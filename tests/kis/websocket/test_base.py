import asyncio
import inspect
import json
from contextlib import suppress
from typing import cast

import pytest
import websockets
from websockets.protocol import State

from app.core.config import Settings
from app.kis.exceptions import KISWebSocketSubscriptionLimitError
from app.kis.schemas import (
    KISTrType,
    KISWebSocketSubscription,
    KISWebSocketTokenResponse,
)
from app.kis.websocket.base import (
    KIS_MAX_SUBSCRIPTIONS,
    KISBaseWebSocketQuote,
)


class FakeWebSocket:
    """네트워크 없이 웹소켓의 수신·송신 동작만 재현한다."""

    def __init__(self, messages: list[str] | None = None) -> None:
        self.messages = list(messages or [])
        self.sent: list[str] = []
        self.pongs: list[str] = []
        self.state = State.OPEN
        self.closed = asyncio.Event()

    def __aiter__(self) -> "FakeWebSocket":
        return self

    async def __anext__(self) -> str:
        if self.messages:
            return self.messages.pop(0)

        await self.closed.wait()
        raise StopAsyncIteration

    async def send(self, message: str) -> None:
        self.sent.append(message)

    async def pong(self, message: str) -> None:
        self.pongs.append(message)

    async def close(self) -> None:
        self.state = State.CLOSED
        self.closed.set()


class DelayedConnection:
    """테스트가 허용할 때까지 연결 완료를 지연한다."""

    def __init__(self, websocket: FakeWebSocket) -> None:
        self.websocket = websocket
        self.started = asyncio.Event()
        self.allow_connection = asyncio.Event()
        self._yielded = False

    def __aiter__(self) -> "DelayedConnection":
        return self

    async def __anext__(self) -> FakeWebSocket:
        if self._yielded:
            await asyncio.Event().wait()

        self.started.set()
        await self.allow_connection.wait()
        self._yielded = True
        return self.websocket


class FailingConnection:
    """반복 시 즉시 치명 오류를 던지는 연결 스텁."""

    def __aiter__(self) -> "FailingConnection":
        return self

    async def __anext__(self) -> FakeWebSocket:
        raise RuntimeError("fatal handshake")


class StubKISWebSocketQuote(KISBaseWebSocketQuote):
    """Base의 보호 구독 API를 테스트에 노출한다."""

    async def subscribe_wire(self, subscription: KISWebSocketSubscription) -> None:
        await self._subscribe(subscription)

    async def unsubscribe_wire(self, subscription: KISWebSocketSubscription) -> None:
        await self._unsubscribe(subscription)


def _make_settings() -> Settings:
    """테스트용 KIS 설정 스텁을 만든다."""

    return cast(
        Settings,
        type(
            "SettingsStub",
            (),
            {
                "kis_virtual": False,
                "kis_app_key": "app-key",
                "kis_app_secret": "app-secret",
                "kis_websocket_domain": "ws://example.test",
                "kis_virtual_websocket_domain": "ws://virtual.example.test",
            },
        )(),
    )


def make_quote(**kwargs: object) -> StubKISWebSocketQuote:
    """테스트용 설정으로 공용 웹소켓 객체를 만든다."""

    token = KISWebSocketTokenResponse(approval_key="approval-key")
    return StubKISWebSocketQuote(
        settings=_make_settings(),
        token=token,
        **kwargs,
    )


def make_subscription(index: int = 0) -> KISWebSocketSubscription:
    """중복되지 않는 테스트용 wire 구독을 만든다."""

    return KISWebSocketSubscription(
        tr_id=f"TR{index:02d}",
        tr_key=f"KEY{index:02d}",
    )


def test_payload_uses_generic_websocket_subscription() -> None:
    quote = make_quote()
    subscription = KISWebSocketSubscription(
        tr_id="H0STCNT0",
        tr_key="005930",
    )

    payload = quote._create_payload(subscription, KISTrType.SUBSCRIBE)

    assert payload.body.input.tr_id == "H0STCNT0"
    assert payload.body.input.tr_key == "005930"


@pytest.mark.asyncio
async def test_run_disables_websocket_protocol_ping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    quote = make_quote()
    connection = DelayedConnection(FakeWebSocket())
    connect_options: dict[str, object] = {}

    def connect_with_captured_options(
        *_args: object,
        **kwargs: object,
    ) -> DelayedConnection:
        connect_options.update(kwargs)
        return connection

    monkeypatch.setattr(
        "app.kis.websocket.base.websockets.connect",
        connect_with_captured_options,
    )

    task = asyncio.create_task(quote.run())
    await connection.started.wait()

    try:
        assert connect_options["ping_interval"] is None
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_pingpong_is_answered_without_entering_stream_queue() -> None:
    message = '{"header":{"tr_id":"PINGPONG","datetime":"20260710171541"}}'
    websocket = FakeWebSocket(messages=[message])
    quote = make_quote()

    receive_task = asyncio.create_task(quote._receive(cast(websockets.ClientConnection, websocket)))
    await asyncio.sleep(0)
    await websocket.close()
    await receive_task

    assert websocket.pongs == [message]
    assert quote._queue.empty()


@pytest.mark.asyncio
async def test_existing_subscription_does_not_hit_limit() -> None:
    quote = make_quote()
    for index in range(KIS_MAX_SUBSCRIPTIONS):
        await quote.subscribe_wire(make_subscription(index))

    await quote.subscribe_wire(make_subscription(0))

    assert len(quote.subscriptions) == KIS_MAX_SUBSCRIPTIONS


@pytest.mark.asyncio
async def test_new_subscription_over_limit_is_rejected() -> None:
    quote = make_quote()
    for index in range(KIS_MAX_SUBSCRIPTIONS):
        await quote.subscribe_wire(make_subscription(index))

    with pytest.raises(KISWebSocketSubscriptionLimitError):
        await quote.subscribe_wire(make_subscription(KIS_MAX_SUBSCRIPTIONS))


def test_subscription_limit_is_not_configurable() -> None:
    parameters = inspect.signature(KISBaseWebSocketQuote.__init__).parameters

    assert "max_subscriptions" not in parameters


@pytest.mark.asyncio
async def test_unsubscribe_removes_requested_subscription() -> None:
    quote = make_quote()
    subscription = make_subscription()
    await quote.subscribe_wire(subscription)

    await quote.unsubscribe_wire(subscription)

    assert quote.subscriptions == frozenset()


@pytest.mark.asyncio
async def test_resubscribe_sends_all_requested_subscriptions() -> None:
    quote = make_quote()
    subscription = make_subscription()
    await quote.subscribe_wire(subscription)
    websocket = FakeWebSocket()

    await quote._resubscribe_all(cast(websockets.ClientConnection, websocket))

    assert len(websocket.sent) == 1
    payload = json.loads(websocket.sent[0])
    assert payload["body"]["input"] == {"tr_id": "TR00", "tr_key": "KEY00"}


def test_full_queue_drops_oldest_message() -> None:
    quote = make_quote(queue_maxsize=2)

    for message in ["a", "b", "c"]:
        quote._enqueue(message)

    drained = [quote._queue.get_nowait() for _ in range(quote._queue.qsize())]
    assert drained == ["b", "c"]
    assert quote.dropped_messages == 1


def test_zero_queue_maxsize_is_rejected() -> None:
    with pytest.raises(ValueError, match="queue_maxsize must be positive"):
        make_quote(queue_maxsize=0)


@pytest.mark.asyncio
async def test_run_propagates_fatal_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    quote = make_quote()
    monkeypatch.setattr(
        "app.kis.websocket.base.websockets.connect",
        lambda *_args, **_kwargs: FailingConnection(),
    )

    with pytest.raises(RuntimeError, match="fatal handshake"):
        await quote.run()


@pytest.mark.asyncio
async def test_stream_yields_enqueued_message() -> None:
    quote = make_quote()
    quote._enqueue("tick")

    message = await asyncio.wait_for(quote.stream().__anext__(), timeout=0.1)

    assert message == "tick"

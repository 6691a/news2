import asyncio
import inspect
import json
import logging
from contextlib import suppress
from typing import cast

import pytest
import websockets
from websockets.protocol import State

from app.core.config import Settings
from app.kis.exceptions import (
    KISWebSocketSubscriptionLimitError,
    KISWebSocketSubscriptionRejectedError,
    KISWebSocketSubscriptionTimeoutError,
)
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


def make_subscription_response(
    *,
    rt_cd: str = "0",
    msg_cd: str = "OPSP0000",
    msg1: str = "SUBSCRIBE SUCCESS",
) -> str:
    """테스트용 KIS 구독 응답 JSON을 만든다.

    Args:
        rt_cd: KIS 성공 또는 실패 코드.
        msg_cd: KIS 응답 메시지 코드.
        msg1: KIS 응답 메시지.

    Returns:
        `TR00`/`KEY00` 구독에 대한 JSON 문자열.
    """

    return json.dumps(
        {
            "header": {"tr_id": "TR00", "tr_key": "KEY00", "encrypt": "N"},
            "body": {"rt_cd": rt_cd, "msg_cd": msg_cd, "msg1": msg1},
        }
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
async def test_subscription_success_is_recorded_without_entering_stream_queue() -> None:
    quote = make_quote()
    subscription = make_subscription()
    await quote.subscribe_wire(subscription)
    websocket = FakeWebSocket(messages=[make_subscription_response()])
    await websocket.close()

    await quote._receive(cast(websockets.ClientConnection, websocket))

    assert quote.active_subscriptions == frozenset({subscription})
    assert quote._queue.empty()


@pytest.mark.asyncio
async def test_subscription_rejection_raises_response_error() -> None:
    quote = make_quote()
    await quote.subscribe_wire(make_subscription())
    websocket = FakeWebSocket(
        messages=[
            make_subscription_response(
                rt_cd="1",
                msg_cd="OPSP9999",
                msg1="INVALID SUBSCRIPTION",
            )
        ]
    )
    await websocket.close()

    with pytest.raises(KISWebSocketSubscriptionRejectedError) as captured:
        await quote._receive(cast(websockets.ClientConnection, websocket))

    assert captured.value.tr_id == "TR00"
    assert captured.value.tr_key == "KEY00"
    assert captured.value.msg_cd == "OPSP9999"
    assert captured.value.msg1 == "INVALID SUBSCRIPTION"


@pytest.mark.asyncio
async def test_already_subscribed_is_treated_as_active(
    caplog: pytest.LogCaptureFixture,
) -> None:
    quote = make_quote()
    subscription = make_subscription()
    await quote.subscribe_wire(subscription)
    websocket = FakeWebSocket(
        messages=[
            make_subscription_response(
                rt_cd="1",
                msg_cd="OPSP0001",
                msg1="ALREADY IN SUBSCRIBE",
            )
        ]
    )
    await websocket.close()

    with caplog.at_level(logging.WARNING, logger="app.kis.websocket.base"):
        await quote._receive(cast(websockets.ClientConnection, websocket))

    assert quote.active_subscriptions == frozenset({subscription})
    assert "ALREADY IN SUBSCRIBE" in caplog.text
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
async def test_run_raises_when_subscription_acknowledgement_times_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    quote = make_quote(subscription_ack_timeout=0.01)
    await quote.subscribe_wire(make_subscription())
    connection = DelayedConnection(FakeWebSocket())
    connection.allow_connection.set()
    monkeypatch.setattr(
        "app.kis.websocket.base.websockets.connect",
        lambda *_args, **_kwargs: connection,
    )

    with pytest.raises(KISWebSocketSubscriptionTimeoutError) as captured:
        await quote.run()

    assert captured.value.pending_subscriptions == frozenset({("TR00", "KEY00")})


@pytest.mark.asyncio
async def test_stream_yields_enqueued_message() -> None:
    quote = make_quote()
    quote._enqueue("tick")

    message = await asyncio.wait_for(quote._stream_raw().__anext__(), timeout=0.1)

    assert message == "tick"

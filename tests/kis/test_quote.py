import asyncio
from contextlib import suppress
from typing import cast

import pytest
from websockets.protocol import State

from app.core.config import Settings
from app.kis.quote import KISWebSocketQuote
from app.kis.schemas import (
    KISWebSocketTokenResponse,
    KISTrId,
    StockCode,
)
from app.kis.schemas.websocket import KISSubscription


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


def make_quote() -> KISWebSocketQuote:
    """테스트용 설정으로 시세 웹소켓 객체를 만든다."""

    token = KISWebSocketTokenResponse(approval_key="approval-key")
    return KISWebSocketQuote(settings=_make_settings(), token=token)


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
        "app.kis.quote.websockets.connect",
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
async def test_pingpong_is_answered_without_entering_the_stream_queue() -> None:
    message = '{"header":{"tr_id":"PINGPONG","datetime":"20260710171541"}}'
    websocket = FakeWebSocket(messages=[message])
    quote = make_quote()

    receive_task = asyncio.create_task(quote._receive(websocket))
    await asyncio.sleep(0)
    await websocket.close()
    await receive_task

    assert websocket.pongs == [message]
    assert quote._queue.empty()


@pytest.mark.asyncio
async def test_existing_subscription_does_not_hit_the_subscription_limit() -> None:
    quote = make_quote()
    subscriptions = [
        KISSubscription(code=code, tr_id=tr_id)
        for code in StockCode
        for tr_id in KISTrId
    ][:40]
    quote._requested_subscriptions.update(subscriptions)
    existing = subscriptions[0]

    await quote.subscribe(code=existing.code, tr_id=existing.tr_id)

    assert len(quote.subscriptions) == 40


@pytest.mark.asyncio
async def test_full_queue_drops_oldest_message() -> None:
    quote = make_quote()
    quote._queue = asyncio.Queue(maxsize=2)

    for text in ["a", "b", "c"]:
        quote._enqueue(text)

    drained = [quote._queue.get_nowait() for _ in range(quote._queue.qsize())]
    assert drained == ["b", "c"]
    assert quote._dropped_messages == 1


def test_zero_queue_maxsize_is_rejected() -> None:
    token = KISWebSocketTokenResponse(approval_key="approval-key")
    with pytest.raises(ValueError):
        KISWebSocketQuote(settings=_make_settings(), token=token, queue_maxsize=0)


@pytest.mark.asyncio
async def test_run_propagates_fatal_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    quote = make_quote()
    monkeypatch.setattr(
        "app.kis.quote.websockets.connect",
        lambda *_args, **_kwargs: FailingConnection(),
    )

    # 치명 오류는 삼키지 않고 전파되어 프로세스가 종료(→ Docker 재시작)된다.
    with pytest.raises(RuntimeError, match="fatal handshake"):
        await quote.run()


@pytest.mark.asyncio
async def test_stream_yields_enqueued_message() -> None:
    quote = make_quote()
    quote._enqueue("tick")

    message = await asyncio.wait_for(quote.stream().__anext__(), timeout=0.1)
    assert message == "tick"

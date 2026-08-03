import asyncio
import inspect
import json
from contextlib import suppress
from typing import cast

import pytest
import websockets
from structlog.testing import capture_logs
from websockets.frames import Close
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
    QUEUE_OVERFLOW_LOG_INTERVAL,
    KISBaseWebSocketQuote,
)
from app.notifications.models import IssueEvent, IssueKind


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


class ClosingWebSocket(FakeWebSocket):
    """서버가 close 프레임을 보내 수신이 끊긴 상황을 재현한다."""

    async def __anext__(self) -> str:
        raise websockets.ConnectionClosedError(Close(1011, "server restart"), None)


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


class RecordingIssueCollector:
    def __init__(self) -> None:
        self.events: list[IssueEvent] = []
        self.recorded = asyncio.Event()

    async def record(self, event: IssueEvent) -> bool:
        self.events.append(event)
        self.recorded.set()
        return True


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


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ('{"header":{"tr_id":"PINGPONG","datetime":"20260710171541"}}', True),
        (
            '{"header":{"tr_id":"TR00","tr_key":"KEY00"},"body":'
            '{"rt_cd":"0","msg_cd":"OPSP0000","msg1":"SUBSCRIBE SUCCESS"}}',
            False,
        ),
        ('{"header":', False),
    ],
)
def test_is_pingpong_validates_control_message(message: str, expected: bool) -> None:
    assert KISBaseWebSocketQuote._is_pingpong(message) is expected


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
async def test_already_subscribed_is_treated_as_active() -> None:
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

    await quote._receive(cast(websockets.ClientConnection, websocket))

    assert quote.active_subscriptions == frozenset({subscription})
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
async def test_subscribe_without_connection_is_logged_as_deferred() -> None:
    quote = make_quote()

    with capture_logs() as logs:
        await quote.subscribe_wire(make_subscription())

    deferred = [entry for entry in logs if entry["event"] == "kis_websocket_subscribe_deferred"]
    assert len(deferred) == 1
    assert deferred[0]["log_level"] == "warning"
    assert (deferred[0]["tr_id"], deferred[0]["tr_key"]) == ("TR00", "KEY00")
    # 전송은 실패했어도 요청 목록에는 남아야 재연결 후 _resubscribe_all이 보낸다.
    assert quote.subscriptions == frozenset({make_subscription()})


@pytest.mark.asyncio
async def test_unsubscribe_without_connection_is_logged_as_deferred() -> None:
    quote = make_quote()
    subscription = make_subscription()
    await quote.subscribe_wire(subscription)

    with capture_logs() as logs:
        await quote.unsubscribe_wire(subscription)

    deferred = [entry for entry in logs if entry["event"] == "kis_websocket_unsubscribe_deferred"]
    assert len(deferred) == 1
    assert deferred[0]["log_level"] == "warning"
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


def test_full_queue_logs_the_first_dropped_message() -> None:
    quote = make_quote(queue_maxsize=1)

    with capture_logs() as logs:
        for message in ["a", "b"]:
            quote._enqueue(message)

    overflow = [entry for entry in logs if entry["event"] == "kis_websocket_queue_overflow"]
    assert len(overflow) == 1
    assert overflow[0]["log_level"] == "warning"
    assert overflow[0]["dropped_total"] == 1
    assert overflow[0]["queue_maxsize"] == 1


def test_full_queue_logs_at_the_configured_interval() -> None:
    quote = make_quote(queue_maxsize=1)

    with capture_logs() as logs:
        for index in range(QUEUE_OVERFLOW_LOG_INTERVAL + 2):
            quote._enqueue(str(index))

    overflow = [entry for entry in logs if entry["event"] == "kis_websocket_queue_overflow"]
    # 유실 1건째와 QUEUE_OVERFLOW_LOG_INTERVAL + 1건째만 남는다.
    assert [entry["dropped_total"] for entry in overflow] == [1, QUEUE_OVERFLOW_LOG_INTERVAL + 1]


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
async def test_run_logs_receive_task_failure_while_it_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    connection = DelayedConnection(websocket)
    connection.allow_connection.set()
    monkeypatch.setattr(
        "app.kis.websocket.base.websockets.connect",
        lambda *_args, **_kwargs: connection,
    )

    with capture_logs() as logs:
        with pytest.raises(KISWebSocketSubscriptionRejectedError):
            await quote.run()

    # suppress(Exception)이던 자리다. 예외는 그대로 올라가되 원인이 로그에 남아야 한다.
    assert [entry["event"] for entry in logs].count("kis_websocket_receive_task_failed") == 1


@pytest.mark.asyncio
async def test_run_logs_connection_closed_before_reconnecting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 짧은 연결 백오프를 0으로 두어 재연결 대기 없이 두 번째 회차로 넘어가게 한다.
    quote = make_quote(reconnect_min_uptime=0.0)
    connection = DelayedConnection(ClosingWebSocket())
    connection.allow_connection.set()
    monkeypatch.setattr(
        "app.kis.websocket.base.websockets.connect",
        lambda *_args, **_kwargs: connection,
    )

    with capture_logs() as logs:
        task = asyncio.create_task(quote.run())
        await asyncio.sleep(0.05)
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    closed = [entry for entry in logs if entry["event"] == "kis_websocket_connection_closed"]
    assert len(closed) == 1
    assert closed[0]["log_level"] == "warning"
    assert closed[0]["code"] == 1011
    assert closed[0]["reason"] == "server restart"
    assert closed[0]["closed_by"] == "server"


@pytest.mark.asyncio
async def test_recoverable_disconnect_records_one_reconnect_issue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collector = RecordingIssueCollector()
    quote = make_quote(
        issue_collector=collector,
        reconnect_min_uptime=0.0,
    )
    connection = DelayedConnection(ClosingWebSocket())
    connection.allow_connection.set()
    monkeypatch.setattr(
        "app.kis.websocket.base.websockets.connect",
        lambda *_args, **_kwargs: connection,
    )

    task = asyncio.create_task(quote.run())
    await asyncio.wait_for(collector.recorded.wait(), timeout=0.2)
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task

    assert len(collector.events) == 1
    event = collector.events[0]
    assert event.kind is IssueKind.WEBSOCKET_RECONNECT
    assert event.service == "kis.websocket"
    assert event.operation == "StubKISWebSocketQuote.run"
    assert event.context == {
        "retry_count": 1,
        "reason_type": "ConnectionClosedError",
    }


@pytest.mark.asyncio
async def test_run_cancellation_does_not_record_reconnect_issue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collector = RecordingIssueCollector()
    quote = make_quote(issue_collector=collector)
    connection = DelayedConnection(FakeWebSocket())
    monkeypatch.setattr(
        "app.kis.websocket.base.websockets.connect",
        lambda *_args, **_kwargs: connection,
    )

    task = asyncio.create_task(quote.run())
    await connection.started.wait()
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task

    assert collector.events == []


@pytest.mark.asyncio
async def test_stream_yields_enqueued_message() -> None:
    quote = make_quote()
    quote._enqueue("tick")

    message = await asyncio.wait_for(quote._stream_raw().__anext__(), timeout=0.1)

    assert message == "tick"

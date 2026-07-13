import asyncio
import json
import logging
from abc import ABC
from collections.abc import AsyncIterator
from contextlib import suppress

import websockets
from websockets.protocol import State

from app.core.config import Settings
from app.kis.exceptions import (
    KISWebSocketNotConnectedError,
    KISWebSocketSubscriptionLimitError,
)
from app.kis.schemas import (
    KISTrType,
    KISWebSocketSubscription,
    KISWebSocketSubscriptionBody,
    KISWebSocketSubscriptionHeader,
    KISWebSocketSubscriptionInput,
    KISWebSocketSubscriptionMessage,
    KISWebSocketTokenResponse,
)

logger = logging.getLogger(__name__)

KIS_MAX_SUBSCRIPTIONS = 40


class KISBaseWebSocketQuote(ABC):
    def __init__(
        self,
        settings: Settings,
        token: KISWebSocketTokenResponse,
        queue_maxsize: int = 10000,
        reconnect_min_uptime: float = 1.0,
        reconnect_max_backoff: float = 30.0,
    ) -> None:
        """설정과 승인 토큰으로 공용 시세 웹소켓 기반을 초기화한다.

        Args:
            settings: KIS 도메인과 계정 환경을 담은 설정.
            token: 실시간 접속에 사용할 승인 키.
            queue_maxsize: 수신 큐 최대 길이.
            reconnect_min_uptime: 짧은 연결로 판단할 기준 시간(초).
            reconnect_max_backoff: 재연결 백오프 상한(초).

        Raises:
            ValueError: queue_maxsize가 0 이하인 경우.
        """

        if queue_maxsize <= 0:
            raise ValueError("queue_maxsize must be positive")

        self.token = token
        self.kis_virtual = settings.kis_virtual
        self.websocket_domain = settings.kis_websocket_domain
        self.virtual_websocket_domain = settings.kis_virtual_websocket_domain

        self._queue_maxsize = queue_maxsize
        self._reconnect_min_uptime = reconnect_min_uptime
        self._reconnect_max_backoff = reconnect_max_backoff

        self._ws: websockets.ClientConnection | None = None
        self._requested_subscriptions: set[KISWebSocketSubscription] = set()
        self._queue: asyncio.Queue[str] = asyncio.Queue(maxsize=queue_maxsize)
        self._dropped_messages = 0
        self._subscription_lock = asyncio.Lock()

    @property
    def subscriptions(self) -> frozenset[KISWebSocketSubscription]:
        """현재 요청된 구독의 불변 스냅샷을 반환한다."""

        return frozenset(self._requested_subscriptions)

    @property
    def dropped_messages(self) -> int:
        """큐 포화로 버려진 메시지 누적 건수를 반환한다."""

        return self._dropped_messages

    def _get_domain(self) -> str:
        """투자 환경에 맞는 웹소켓 도메인을 반환한다."""

        if self.kis_virtual:
            return self.virtual_websocket_domain
        return self.websocket_domain

    def _create_payload(
        self,
        subscription: KISWebSocketSubscription,
        tr_type: KISTrType,
    ) -> KISWebSocketSubscriptionMessage:
        """공용 구독 정보로 KIS 구독 또는 해지 메시지를 생성한다.

        Args:
            subscription: 전송 가능한 TR ID와 TR key를 담은 구독.
            tr_type: 구독 또는 구독 해지 구분.

        Returns:
            승인 키와 구독 입력이 채워진 KIS 메시지.
        """

        return KISWebSocketSubscriptionMessage(
            header=KISWebSocketSubscriptionHeader(
                approval_key=self.token.approval_key,
                tr_type=tr_type,
            ),
            body=KISWebSocketSubscriptionBody(
                input=KISWebSocketSubscriptionInput(
                    tr_id=subscription.tr_id,
                    tr_key=subscription.tr_key,
                )
            ),
        )

    def _get_connection(self) -> websockets.ClientConnection:
        """현재 열린 웹소켓 연결을 반환한다.

        Raises:
            KISWebSocketNotConnectedError: 연결이 없거나 닫힌 경우.
        """

        ws = self._ws
        if ws is None or ws.state is not State.OPEN:
            raise KISWebSocketNotConnectedError
        return ws

    def _enqueue(self, message: str) -> None:
        """큐가 가득 차면 가장 오래된 메시지를 버리고 새 메시지를 넣는다.

        Args:
            message: 큐에 넣을 수신 원문.
        """

        if self._queue.full():
            with suppress(asyncio.QueueEmpty):
                self._queue.get_nowait()
            self._dropped_messages += 1
        self._queue.put_nowait(message)

    async def _send(
        self,
        subscription: KISWebSocketSubscription,
        tr_type: KISTrType,
        ws: websockets.ClientConnection | None = None,
    ) -> None:
        """지정한 연결에 구독 또는 구독 해지 메시지를 전송한다.

        Args:
            subscription: 전송할 공용 웹소켓 구독.
            tr_type: 구독 또는 구독 해지 구분.
            ws: 전송에 사용할 연결. 생략하면 현재 연결을 사용한다.

        Raises:
            KISWebSocketNotConnectedError: 사용할 열린 연결이 없는 경우.
        """

        connection = ws if ws is not None else self._get_connection()
        payload = self._create_payload(subscription, tr_type).model_dump_json()
        await connection.send(payload)

    async def _resubscribe_all(self, ws: websockets.ClientConnection) -> None:
        """새 연결에 현재 요청된 구독을 모두 다시 등록한다.

        Args:
            ws: 재구독 메시지를 보낼 새 연결.
        """

        async with self._subscription_lock:
            for subscription in tuple(self._requested_subscriptions):
                await self._send(subscription, KISTrType.SUBSCRIBE, ws=ws)

    async def _subscribe(self, subscription: KISWebSocketSubscription) -> None:
        """공용 구독을 요청 목록에 추가하고 연결 중이면 전송한다.

        Args:
            subscription: 추가할 전송 가능한 구독.

        Raises:
            KISWebSocketSubscriptionLimitError: 신규 구독이 한도를 넘는 경우.
        """

        async with self._subscription_lock:
            if subscription in self._requested_subscriptions:
                return

            if len(self._requested_subscriptions) >= KIS_MAX_SUBSCRIPTIONS:
                raise KISWebSocketSubscriptionLimitError(KIS_MAX_SUBSCRIPTIONS)

            self._requested_subscriptions.add(subscription)

            try:
                await self._send(subscription, KISTrType.SUBSCRIBE)
            except (KISWebSocketNotConnectedError, websockets.ConnectionClosed):
                pass

    async def _unsubscribe(self, subscription: KISWebSocketSubscription) -> None:
        """공용 구독을 요청 목록에서 제거하고 연결 중이면 해지한다.

        Args:
            subscription: 제거할 전송 가능한 구독.
        """

        async with self._subscription_lock:
            if subscription not in self._requested_subscriptions:
                return

            self._requested_subscriptions.discard(subscription)

            try:
                await self._send(subscription, KISTrType.UNSUBSCRIBE)
            except (KISWebSocketNotConnectedError, websockets.ConnectionClosed):
                pass

    async def run(self) -> None:
        """연결, 수신, 재구독 및 무한 재연결을 실행한다."""

        loop = asyncio.get_running_loop()
        short_streak = 0

        async for ws in websockets.connect(self._get_domain(), ping_interval=None):
            self._ws = ws
            started = loop.time()
            try:
                await self._resubscribe_all(ws)
                await self._receive(ws)
            except websockets.ConnectionClosed:
                pass
            finally:
                self._ws = None

            if loop.time() - started < self._reconnect_min_uptime:
                short_streak += 1
                delay = min(2 ** (short_streak - 1), self._reconnect_max_backoff)
                logger.warning(
                    "KIS WebSocket reconnecting in %ss (streak %s)",
                    delay,
                    short_streak,
                )
                await asyncio.sleep(delay)
            else:
                short_streak = 0

    async def _receive(self, ws: websockets.ClientConnection) -> None:
        """메시지를 수신해 PINGPONG은 응답하고 나머지는 큐로 넘긴다.

        Args:
            ws: 메시지를 읽을 연결.
        """

        async for message in ws:
            if isinstance(message, bytes):
                message = message.decode("utf-8")

            if self._is_pingpong(message):
                await ws.pong(message)
                continue

            self._enqueue(message)

    @staticmethod
    def _is_pingpong(message: str) -> bool:
        """수신 원문이 KIS PINGPONG 제어 메시지인지 반환한다."""

        if not message.startswith("{"):
            return False

        try:
            payload = json.loads(message)
        except json.JSONDecodeError:
            return False

        header = payload.get("header")
        return isinstance(header, dict) and header.get("tr_id") == "PINGPONG"

    async def stream(self) -> AsyncIterator[str]:
        """수신 큐의 원문 메시지를 도착 순서대로 내보낸다.

        Yields:
            큐에 도착한 원문 문자열.
        """

        while True:
            yield await self._queue.get()

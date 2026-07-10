import asyncio
import json
import logging
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
    KISWebSocketTokenResponse,
    KISWebSocketSubscriptionBody,
    KISWebSocketSubscriptionHeader,
    KISWebSocketSubscriptionMessage,
    KISTrType,
    KISWebSocketSubscriptionInput,
    KISTrId,
    StockCode,
)
from app.kis.schemas.websocket import KISSubscription

logger = logging.getLogger(__name__)


class KISWebSocketQuote:
    def __init__(
        self,
        settings: Settings,
        token: KISWebSocketTokenResponse,
        max_subscriptions: int = 40,
        queue_maxsize: int = 10000,
        reconnect_min_uptime: float = 1.0,
        reconnect_max_backoff: float = 30.0,
    ) -> None:
        """설정과 승인 토큰으로 시세 웹소켓 클라이언트를 초기화한다.

        Args:
            settings: KIS 도메인·앱 키 등 접속 설정.
            token: 실시간 접속에 사용할 승인 키를 담은 토큰.
            max_subscriptions: 동시에 요청할 수 있는 최대 구독 수.
            queue_maxsize: 수신 큐 최대 길이. 초과하면 오래된 메시지를 버린다.
            reconnect_min_uptime: 이보다 짧게 유지된 연결(초)은 tight loop로 보고 백오프한다.
            reconnect_max_backoff: 재연결 백오프 상한(초).

        Raises:
            ValueError: queue_maxsize가 0 이하인 경우(무제한 큐 방지).
        """

        if queue_maxsize <= 0:
            raise ValueError("queue_maxsize must be positive")

        self.token = token

        self.kis_virtual = settings.kis_virtual
        self.websocket_domain = settings.kis_websocket_domain
        self.virtual_websocket_domain = settings.kis_virtual_websocket_domain

        self._max_subscriptions = max_subscriptions
        self._queue_maxsize = queue_maxsize
        self._reconnect_min_uptime = reconnect_min_uptime
        self._reconnect_max_backoff = reconnect_max_backoff

        self._ws: websockets.ClientConnection | None = None
        self._requested_subscriptions: set[KISSubscription] = set()
        self._queue: asyncio.Queue[str] = asyncio.Queue(maxsize=queue_maxsize)
        self._dropped_messages = 0
        # 구독 set 변경과 재구독 전송을 직렬화해 SUBSCRIBE↔UNSUBSCRIBE 뒤집힘을 막는다.
        self._subscription_lock = asyncio.Lock()

    @property
    def subscriptions(self) -> frozenset[KISSubscription]:
        """현재 '요청된'(서버 ACK 확인 전) 구독의 불변 스냅샷을 반환한다."""

        return frozenset(self._requested_subscriptions)

    @property
    def dropped_messages(self) -> int:
        """큐 포화로 버려진 메시지 누적 건수."""

        return self._dropped_messages

    def _get_domain(self) -> str:
        """가상 투자 여부에 맞는 웹소켓 도메인을 반환한다.

        Returns:
            가상 투자면 모의 도메인, 아니면 실전 도메인 문자열.
        """

        if self.kis_virtual:
            return self.virtual_websocket_domain
        return self.websocket_domain

    def _create_payload(
        self, code: StockCode, tr_type: KISTrType, tr_id: KISTrId
    ) -> KISWebSocketSubscriptionMessage:
        """KIS 구독 또는 구독 해지 메시지를 생성한다.

        Args:
            code: 대상 종목 코드.
            tr_type: 구독 또는 구독 해지 구분.
            tr_id: 시장 구분을 포함한 실시간 체결 tr_id.

        Returns:
            헤더와 입력이 채워진 구독 메시지 모델.
        """

        return KISWebSocketSubscriptionMessage(
            header=KISWebSocketSubscriptionHeader(
                approval_key=self.token.approval_key,
                tr_type=tr_type,
            ),
            body=KISWebSocketSubscriptionBody(
                input=KISWebSocketSubscriptionInput(
                    tr_id=tr_id,
                    tr_key=code,
                )
            ),
        )

    def _get_connection(self) -> websockets.ClientConnection:
        """현재 열려 있는 연결을 반환한다.

        Returns:
            OPEN 상태인 웹소켓 연결.

        Raises:
            KISWebSocketNotConnectedError: 연결이 없거나 이미 닫힌 경우.
        """

        ws = self._ws
        if ws is None or ws.state is not State.OPEN:
            raise KISWebSocketNotConnectedError
        return ws

    def _enqueue(self, message: str) -> None:
        """큐가 가득 차면 가장 오래된 메시지를 버리고 새 메시지를 넣는다.

        블로킹 없이 넣으므로 소비자가 느려도 _receive가 멈추지 않고(=PINGPONG
        응답이 밀리지 않고), 메모리도 queue_maxsize로 유한하게 유지된다.

        Args:
            message: 큐에 넣을 수신 메시지.
        """

        if self._queue.full():
            with suppress(asyncio.QueueEmpty):
                self._queue.get_nowait()
            self._dropped_messages += 1
        self._queue.put_nowait(message)

    async def _send(
        self,
        code: StockCode,
        tr_type: KISTrType,
        tr_id: KISTrId = KISTrId.STOCK_TRADE_KRX,
        ws: websockets.ClientConnection | None = None,
    ) -> None:
        """지정한(또는 현재) 연결에 구독·해지 메시지를 전송한다.

        Args:
            code: 대상 종목 코드.
            tr_type: 구독 또는 구독 해지 구분.
            tr_id: 시장 구분을 포함한 tr_id.
            ws: 전송에 사용할 연결. 생략하면 현재 열린 연결을 사용한다.

        Raises:
            KISWebSocketNotConnectedError: ws가 없고 현재 연결도 닫힌 경우.
        """

        connection = ws if ws is not None else self._get_connection()
        payload = self._create_payload(
            code=code,
            tr_type=tr_type,
            tr_id=tr_id,
        ).model_dump_json()
        await connection.send(payload)

    async def _resubscribe_all(self, ws: websockets.ClientConnection) -> None:
        """재연결한 소켓에 요청된 모든 구독을 다시 등록한다.

        Args:
            ws: 재구독 메시지를 보낼 새 연결.
        """

        # 락으로 subscribe()/unsubscribe()와 직렬화해 재구독 도중 순서가
        # 뒤집히지 않게 한다. 스냅샷도 락 안에서 떠 일관성을 보장한다.
        async with self._subscription_lock:
            for subscription in tuple(self._requested_subscriptions):
                await self._send(
                    code=subscription.code,
                    tr_type=KISTrType.SUBSCRIBE,
                    tr_id=subscription.tr_id,
                    ws=ws,
                )

    async def run(self) -> None:
        """연결·수신·무한 재연결을 실행한다. 엔트리포인트가 직접 await한다.

        일시적 끊김은 `websockets.connect` 이터레이터가 인프로세스로 재연결한다.
        반면 치명 오류(잘못된 URI/토큰 등)는 잡지 않고 호출자에게 전파한다.
        독립 프로세스에서는 그대로 종료되어 Docker `restart: always`가 새로
        띄운다. KIS는 JSON PINGPONG을 직접 처리하므로 라이브러리 keepalive는 끈다.
        """

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

            # 연결이 곧바로 끊기는 tight loop를 지수 백오프로 완화한다.
            if loop.time() - started < self._reconnect_min_uptime:
                short_streak += 1
                delay = min(2 ** (short_streak - 1), self._reconnect_max_backoff)
                logger.warning(
                    "KIS WebSocket reconnecting in %ss (streak %s)", delay, short_streak
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

            # KIS PINGPONG은 소비자에게 넘기지 않고 즉시 응답해야 연결이 유지된다.
            if self._is_pingpong(message):
                await ws.pong(message)
                continue

            self._enqueue(message)

    @staticmethod
    def _is_pingpong(message: str) -> bool:
        """메시지가 KIS PINGPONG 제어 메시지인지 판단한다.

        Args:
            message: 수신한 원본 문자열.

        Returns:
            PINGPONG이면 True, 아니면 False.
        """

        if not message.startswith("{"):
            return False

        try:
            payload = json.loads(message)
        except json.JSONDecodeError:
            return False

        header = payload.get("header")
        return isinstance(header, dict) and header.get("tr_id") == "PINGPONG"

    async def subscribe(
        self,
        code: StockCode,
        tr_id: KISTrId = KISTrId.STOCK_TRADE_KRX,
    ) -> None:
        """종목을 구독 목록에 추가하고 연결 중이면 즉시 전송한다.

        Args:
            code: 구독할 종목 코드.
            tr_id: 시장 구분을 포함한 tr_id. 기본값은 KRX 체결.

        Raises:
            KISWebSocketSubscriptionLimitError: 신규 구독이 한도를 넘는 경우.
        """

        subscription = KISSubscription(code=code, tr_id=tr_id)

        async with self._subscription_lock:
            # 이미 요청한 구독은 한도 검사와 중복 전송을 하지 않는다.
            if subscription in self._requested_subscriptions:
                return

            if len(self._requested_subscriptions) >= self._max_subscriptions:
                raise KISWebSocketSubscriptionLimitError(self._max_subscriptions)

            self._requested_subscriptions.add(subscription)

            try:
                await self._send(code, KISTrType.SUBSCRIBE, tr_id)
            except (KISWebSocketNotConnectedError, websockets.ConnectionClosed):
                # 요청 목록에 남아 있으므로 다음 연결에서 _resubscribe_all()이 처리한다.
                pass

    async def unsubscribe(
        self,
        code: StockCode,
        tr_id: KISTrId = KISTrId.STOCK_TRADE_KRX,
    ) -> None:
        """종목을 구독 목록에서 제거하고 연결 중이면 즉시 해지를 전송한다.

        Args:
            code: 구독 해지할 종목 코드.
            tr_id: 시장 구분을 포함한 tr_id. 기본값은 KRX 체결.
        """

        subscription = KISSubscription(code=code, tr_id=tr_id)

        async with self._subscription_lock:
            if subscription not in self._requested_subscriptions:
                return

            self._requested_subscriptions.discard(subscription)

            try:
                await self._send(code, KISTrType.UNSUBSCRIBE, tr_id)
            except (KISWebSocketNotConnectedError, websockets.ConnectionClosed):
                pass

    async def stream(self) -> AsyncIterator[str]:
        """수신 큐의 메시지를 도착 순서대로 내보낸다.

        프로세스 종료 시 소비 태스크가 취소되며 자연히 끝난다.

        Yields:
            큐에 도착한 순서대로의 원본 메시지 문자열.
        """

        while True:
            yield await self._queue.get()

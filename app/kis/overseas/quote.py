import logging
from collections.abc import AsyncIterator

from app.kis.overseas.schemas import (
    KISOverseasOrderbook,
    KISOverseasSubscription,
    KISOverseasTrade,
    parse_frame,
)
from app.kis.websocket.base import KISBaseWebSocketQuote

logger = logging.getLogger(__name__)


class KISOverseasWebSocketQuote(KISBaseWebSocketQuote):
    async def subscribe(self, subscription: KISOverseasSubscription) -> None:
        """미국주식 실시간 시세 구독을 요청한다.

        Args:
            subscription: 미국 종목, 거래소와 실시간 TR을 담은 구독 요청.
        """

        await self._subscribe(subscription.to_websocket_subscription())

    async def unsubscribe(self, subscription: KISOverseasSubscription) -> None:
        """미국주식 실시간 시세 구독을 해지한다.

        Args:
            subscription: 해지할 미국 종목, 거래소와 실시간 TR 구독.
        """

        await self._unsubscribe(subscription.to_websocket_subscription())

    async def stream(self) -> AsyncIterator[KISOverseasTrade | KISOverseasOrderbook]:
        """해외주식 원문 프레임을 파싱한 DTO로 낱개씩 내보낸다.

        Yields:
            체결 또는 호가 DTO.
        """

        async for raw in self._stream_raw():
            try:
                events = parse_frame(raw)
            except ValueError as error:
                logger.warning(
                    "Invalid KIS overseas WebSocket frame skipped: %s; raw=%r",
                    error,
                    raw[:200],
                )
                continue

            if events is None:
                continue

            for event in events:
                yield event

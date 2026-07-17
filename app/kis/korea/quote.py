from collections.abc import AsyncIterator

from app.core.logging import get_logger
from app.kis.korea.schemas import (
    KISKoreaOrderbook,
    KISKoreaSubscription,
    KISKoreaTrade,
    parse_frame,
)
from app.kis.websocket.base import KISBaseWebSocketQuote

logger = get_logger(__name__)


class KISKoreaWebSocketQuote(KISBaseWebSocketQuote):
    async def subscribe(self, subscription: KISKoreaSubscription) -> None:
        """한국주식 실시간 시세 구독을 요청한다.

        Args:
            subscription: 한국 종목과 실시간 TR을 담은 구독 요청.
        """

        await self._subscribe(subscription.to_websocket_subscription())

    async def unsubscribe(self, subscription: KISKoreaSubscription) -> None:
        """한국주식 실시간 시세 구독을 해지한다.

        Args:
            subscription: 해지할 한국 종목과 실시간 TR 구독.
        """

        await self._unsubscribe(subscription.to_websocket_subscription())

    async def stream(self) -> AsyncIterator[KISKoreaTrade | KISKoreaOrderbook]:
        """한국주식 원문 프레임을 파싱한 DTO로 낱개씩 내보낸다.

        Yields:
            체결 또는 호가 DTO.
        """

        async for raw in self._stream_raw():
            try:
                events = parse_frame(raw)
            except ValueError as error:
                logger.warning(
                    "invalid_kis_korea_websocket_frame",
                    error=str(error),
                    raw=raw[:200],
                )
                continue

            if events is None:
                continue

            for event in events:
                yield event

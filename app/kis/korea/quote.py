from app.kis.korea.schemas import KISKoreaSubscription
from app.kis.websocket.base import KISBaseWebSocketQuote


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

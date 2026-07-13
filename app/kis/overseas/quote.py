from app.kis.overseas.schemas import KISOverseasSubscription
from app.kis.websocket.base import KISBaseWebSocketQuote


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

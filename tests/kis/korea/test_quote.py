from typing import cast

import pytest

from app.core.config import Settings
from app.kis.korea.quote import KISKoreaWebSocketQuote
from app.kis.korea.schemas import (
    KISKoreaStockCode,
    KISKoreaSubscription,
    KISKoreaTrId,
)
from app.kis.schemas import KISWebSocketSubscription, KISWebSocketTokenResponse


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


def make_quote() -> KISKoreaWebSocketQuote:
    """테스트용 한국주식 웹소켓 객체를 만든다."""

    token = KISWebSocketTokenResponse(approval_key="approval-key")
    return KISKoreaWebSocketQuote(settings=_make_settings(), token=token)


@pytest.mark.asyncio
async def test_korea_subscribe_stores_websocket_subscription() -> None:
    quote = make_quote()
    subscription = KISKoreaSubscription(
        code=KISKoreaStockCode.SAMSUNG_ELECTRONICS,
        tr_id=KISKoreaTrId.STOCK_TRADE_KRX,
    )

    await quote.subscribe(subscription)

    assert quote.subscriptions == frozenset({KISWebSocketSubscription(tr_id="H0STCNT0", tr_key="005930")})


@pytest.mark.asyncio
async def test_korea_unsubscribe_removes_websocket_subscription() -> None:
    quote = make_quote()
    subscription = KISKoreaSubscription(
        code=KISKoreaStockCode.SK_HYNIX,
        tr_id=KISKoreaTrId.STOCK_TRADE_UNIFIED,
    )
    await quote.subscribe(subscription)

    await quote.unsubscribe(subscription)

    assert quote.subscriptions == frozenset()


@pytest.mark.asyncio
async def test_trade_and_orderbook_for_same_stock_are_distinct() -> None:
    quote = make_quote()
    await quote.subscribe(
        KISKoreaSubscription(
            code=KISKoreaStockCode.SAMSUNG_ELECTRONICS,
            tr_id=KISKoreaTrId.STOCK_TRADE_KRX,
        )
    )
    await quote.subscribe(
        KISKoreaSubscription(
            code=KISKoreaStockCode.SAMSUNG_ELECTRONICS,
            tr_id=KISKoreaTrId.STOCK_ORDERBOOK_KRX,
        )
    )

    assert len(quote.subscriptions) == 2

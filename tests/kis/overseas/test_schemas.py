from app.kis.overseas.schemas import (
    KISOverseasMarket,
    KISOverseasStockCode,
    KISOverseasSubscription,
    KISOverseasTrId,
)
from app.kis.schemas.websocket import KISWebSocketSubscription


def test_overseas_stock_codes_are_preserved() -> None:
    assert KISOverseasStockCode.APPLE == "AAPL"
    assert KISOverseasStockCode.ALPHABET == "GOOGL"
    assert KISOverseasStockCode.MICROSOFT == "MSFT"
    assert KISOverseasStockCode.META == "META"
    assert KISOverseasStockCode.NVIDIA == "NVDA"
    assert KISOverseasStockCode.QQQ == "QQQ"
    assert KISOverseasStockCode.SP500 == "SPY"


def test_overseas_tr_ids_are_limited_to_us_quotes() -> None:
    assert KISOverseasTrId.TRADE == "HDFSCNT0"
    assert KISOverseasTrId.ORDERBOOK == "HDFSASP0"
    assert "DELAYED_ORDERBOOK_ASIA" not in KISOverseasTrId.__members__


def test_supported_us_markets_use_kis_codes() -> None:
    assert set(KISOverseasMarket) == {
        KISOverseasMarket.NASDAQ,
        KISOverseasMarket.NYSE,
        KISOverseasMarket.AMEX,
    }
    assert KISOverseasMarket.NASDAQ == "NAS"
    assert KISOverseasMarket.NYSE == "NYS"
    assert KISOverseasMarket.AMEX == "AMS"


def test_nasdaq_trade_subscription_builds_kis_tr_key() -> None:
    subscription = KISOverseasSubscription(
        code=KISOverseasStockCode.APPLE,
        market=KISOverseasMarket.NASDAQ,
        tr_id=KISOverseasTrId.TRADE,
    )

    assert subscription.to_websocket_subscription() == KISWebSocketSubscription(
        tr_id="HDFSCNT0",
        tr_key="DNASAAPL",
    )


def test_amex_orderbook_subscription_builds_kis_tr_key() -> None:
    subscription = KISOverseasSubscription(
        code=KISOverseasStockCode.SP500,
        market=KISOverseasMarket.AMEX,
        tr_id=KISOverseasTrId.ORDERBOOK,
    )

    assert subscription.to_websocket_subscription() == KISWebSocketSubscription(
        tr_id="HDFSASP0",
        tr_key="DAMSSPY",
    )


def test_overseas_subscription_is_hashable() -> None:
    subscription = KISOverseasSubscription(
        code=KISOverseasStockCode.NVIDIA,
        market=KISOverseasMarket.NASDAQ,
        tr_id=KISOverseasTrId.TRADE,
    )

    assert {subscription} == {subscription}

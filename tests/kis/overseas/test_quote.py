import asyncio
import logging
from typing import cast

import pytest

from app.core.config import Settings
from app.kis.overseas.quote import KISOverseasWebSocketQuote
from app.kis.overseas.schemas import (
    KISOverseasMarket,
    KISOverseasStockCode,
    KISOverseasSubscription,
    KISOverseasTrade,
    KISOverseasTrId,
)
from app.kis.schemas import KISWebSocketSubscription, KISWebSocketTokenResponse
from tests.kis.overseas.fixtures import GOOGL_TRADE_FRAMES, SUBSCRIBE_SUCCESS_TRADE


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


def make_quote() -> KISOverseasWebSocketQuote:
    """테스트용 미국주식 웹소켓 객체를 만든다."""

    token = KISWebSocketTokenResponse(approval_key="approval-key")
    return KISOverseasWebSocketQuote(settings=_make_settings(), token=token)


def make_subscription(tr_id: KISOverseasTrId) -> KISOverseasSubscription:
    """애플 NASDAQ 테스트 구독을 만든다."""

    return KISOverseasSubscription(
        code=KISOverseasStockCode.APPLE,
        market=KISOverseasMarket.NASDAQ,
        tr_id=tr_id,
    )


@pytest.mark.asyncio
async def test_overseas_subscribe_stores_websocket_subscription() -> None:
    quote = make_quote()

    await quote.subscribe(make_subscription(KISOverseasTrId.TRADE))

    assert quote.subscriptions == frozenset({KISWebSocketSubscription(tr_id="HDFSCNT0", tr_key="DNASAAPL")})


@pytest.mark.asyncio
async def test_overseas_unsubscribe_removes_websocket_subscription() -> None:
    quote = make_quote()
    subscription = make_subscription(KISOverseasTrId.TRADE)
    await quote.subscribe(subscription)

    await quote.unsubscribe(subscription)

    assert quote.subscriptions == frozenset()


@pytest.mark.asyncio
async def test_trade_and_orderbook_for_same_us_stock_are_distinct() -> None:
    quote = make_quote()

    await quote.subscribe(make_subscription(KISOverseasTrId.TRADE))
    await quote.subscribe(make_subscription(KISOverseasTrId.ORDERBOOK))

    assert quote.subscriptions == frozenset(
        {
            KISWebSocketSubscription(tr_id="HDFSCNT0", tr_key="DNASAAPL"),
            KISWebSocketSubscription(tr_id="HDFSASP0", tr_key="DNASAAPL"),
        }
    )


@pytest.mark.asyncio
async def test_stream_yields_parsed_overseas_trade() -> None:
    quote = make_quote()
    quote._enqueue(GOOGL_TRADE_FRAMES[0])

    event = await asyncio.wait_for(anext(quote.stream()), timeout=0.1)

    assert isinstance(event, KISOverseasTrade)
    assert event.symbol == "GOOGL"


@pytest.mark.asyncio
async def test_stream_skips_overseas_json_control_message() -> None:
    quote = make_quote()
    quote._enqueue(SUBSCRIBE_SUCCESS_TRADE)
    quote._enqueue(GOOGL_TRADE_FRAMES[0])

    event = await asyncio.wait_for(anext(quote.stream()), timeout=0.1)

    assert isinstance(event, KISOverseasTrade)


@pytest.mark.asyncio
async def test_stream_warns_and_continues_after_invalid_overseas_frame(
    caplog: pytest.LogCaptureFixture,
) -> None:
    quote = make_quote()
    quote._enqueue("0|HDFSCNT0|001|short-body")
    quote._enqueue(GOOGL_TRADE_FRAMES[0])

    with caplog.at_level(logging.WARNING, logger="app.kis.overseas.quote"):
        event = await asyncio.wait_for(anext(quote.stream()), timeout=0.1)

    assert isinstance(event, KISOverseasTrade)
    assert "short-body" in caplog.text

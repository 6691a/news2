from datetime import date, time
from decimal import Decimal

import pytest

import app.kis.korea as korea_package
from app.kis.korea.schemas import (
    KISKoreaOrderbook,
    KISKoreaOrderbookLevel,
    KISKoreaStockCode,
    KISKoreaSubscription,
    KISKoreaTrade,
    KISKoreaTrId,
    parse_frame,
)
from app.kis.schemas.websocket import KISWebSocketSubscription
from tests.kis.korea.fixtures import (
    SK_HYNIX_ORDERBOOK_FRAMES,
    SK_HYNIX_TRADE_FRAMES,
    SUBSCRIBE_SUCCESS_ORDERBOOK,
    SUBSCRIBE_SUCCESS_TRADE,
)


def _body_fields(frame: str) -> list[str]:
    """웹소켓 fixture에서 본문 필드만 분리한다."""

    return frame.split("|", 3)[3].split("^")


def test_korea_subscription_converts_to_websocket_subscription() -> None:
    subscription = KISKoreaSubscription(
        code=KISKoreaStockCode.SAMSUNG_ELECTRONICS,
        tr_id=KISKoreaTrId.STOCK_TRADE_KRX,
    )

    assert subscription.to_websocket_subscription() == KISWebSocketSubscription(
        tr_id="H0STCNT0",
        tr_key="005930",
    )


def test_korea_subscription_is_hashable() -> None:
    subscription = KISKoreaSubscription(
        code=KISKoreaStockCode.SK_HYNIX,
        tr_id=KISKoreaTrId.STOCK_ORDERBOOK_UNIFIED,
    )

    assert {subscription} == {subscription}


def test_korea_trade_parses_all_typed_values() -> None:
    trade = KISKoreaTrade.from_body(_body_fields(SK_HYNIX_TRADE_FRAMES[0]))

    assert trade.stock_code == "000660"
    assert trade.trade_time == time(10, 39, 25)
    assert trade.current_price == Decimal("1996000")
    assert trade.weighted_average_price == Decimal("2049536.80")
    assert trade.trade_volume == 20
    assert trade.cumulative_volume == 2388396
    assert trade.business_date == date(2026, 7, 13)
    assert trade.market_operation_code is None


def test_korea_trade_rejects_wrong_field_count() -> None:
    fields = _body_fields(SK_HYNIX_TRADE_FRAMES[0])[:-1]

    with pytest.raises(ValueError, match="46"):
        KISKoreaTrade.from_body(fields)


def test_korea_orderbook_groups_ten_levels_and_parses_metadata() -> None:
    orderbook = KISKoreaOrderbook.from_body(_body_fields(SK_HYNIX_ORDERBOOK_FRAMES[0]))

    assert len(orderbook.levels) == 10
    assert orderbook.levels[0].ask_price == Decimal("1996000")
    assert orderbook.levels[0].bid_price == Decimal("1995000")
    assert orderbook.levels[0].ask_quantity == 49
    assert orderbook.levels[0].bid_quantity == 30
    assert orderbook.levels[9].ask_price == Decimal("2005000")
    assert orderbook.levels[9].bid_price == Decimal("1986000")
    assert orderbook.levels[9].ask_quantity == 279
    assert orderbook.levels[9].bid_quantity == 1527
    assert orderbook.total_ask_quantity == 4753
    assert orderbook.total_bid_quantity == 4253
    assert orderbook.cumulative_volume == 2388421
    assert orderbook.krx_mid_price == Decimal("1995500")


def test_korea_orderbook_rejects_wrong_field_count() -> None:
    fields = _body_fields(SK_HYNIX_ORDERBOOK_FRAMES[0])[:-1]

    with pytest.raises(ValueError, match="62"):
        KISKoreaOrderbook.from_body(fields)


@pytest.mark.parametrize(
    "message",
    [SUBSCRIBE_SUCCESS_ORDERBOOK, SUBSCRIBE_SUCCESS_TRADE],
)
def test_parse_frame_ignores_json_control_messages(message: str) -> None:
    assert parse_frame(message) is None


@pytest.mark.parametrize("frame", SK_HYNIX_TRADE_FRAMES)
def test_parse_frame_parses_trade_fixture(frame: str) -> None:
    parsed = parse_frame(frame)

    assert parsed is not None
    assert len(parsed) == 1
    assert isinstance(parsed[0], KISKoreaTrade)


@pytest.mark.parametrize("frame", SK_HYNIX_ORDERBOOK_FRAMES)
def test_parse_frame_parses_orderbook_fixture(frame: str) -> None:
    parsed = parse_frame(frame)

    assert parsed is not None
    assert len(parsed) == 1
    assert isinstance(parsed[0], KISKoreaOrderbook)


def test_parse_frame_splits_multiple_trade_records() -> None:
    bodies = [frame.split("|", 3)[3] for frame in SK_HYNIX_TRADE_FRAMES]
    frame = f"0|H0STCNT0|003|{'^'.join(bodies)}"

    parsed = parse_frame(frame)

    assert parsed is not None
    assert [trade.cumulative_volume for trade in parsed] == [
        2388396,
        2388402,
        2388403,
    ]


@pytest.mark.parametrize(
    ("frame", "message"),
    [
        ("0|UNKNOWN|001|value", "Unsupported"),
        ("0|H0STCNT0|abc|value", "record count"),
        ("0|H0STCNT0|000|value", "positive"),
        ("0|H0STCNT0|001|value", "46"),
    ],
)
def test_parse_frame_rejects_malformed_data_frames(
    frame: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        parse_frame(frame)


def test_korea_package_reexports_websocket_dtos_and_parser() -> None:
    assert korea_package.KISKoreaTrade is KISKoreaTrade
    assert korea_package.KISKoreaOrderbook is KISKoreaOrderbook
    assert korea_package.KISKoreaOrderbookLevel is KISKoreaOrderbookLevel
    assert korea_package.parse_frame is parse_frame

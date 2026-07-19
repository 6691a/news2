from datetime import date, time
from decimal import Decimal

import pytest

import app.kis.overseas as overseas_package
from app.kis.overseas.schemas import (
    KISOverseasMarket,
    KISOverseasOrderbook,
    KISOverseasOrderbookLevel,
    KISOverseasSubscription,
    KISOverseasTrade,
    KISOverseasTrId,
    parse_frame,
)
from app.kis.schemas.websocket import KISWebSocketSubscription
from tests.kis.overseas.fixtures import (
    GOOGL_TRADE_FRAMES,
    SPY_ORDERBOOK_FRAMES,
    SPY_TRADE_FRAMES,
    SUBSCRIBE_SUCCESS_ORDERBOOK,
    SUBSCRIBE_SUCCESS_TRADE,
)


def _body_fields(frame: str) -> list[str]:
    """웹소켓 fixture에서 본문 필드만 분리한다."""

    return frame.split("|", 3)[3].split("^")


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
        code="AAPL",
        market=KISOverseasMarket.NASDAQ,
        tr_id=KISOverseasTrId.TRADE,
    )

    assert subscription.to_websocket_subscription() == KISWebSocketSubscription(
        tr_id="HDFSCNT0",
        tr_key="DNASAAPL",
    )


def test_overseas_subscription_accepts_ticker_not_declared_in_code() -> None:
    subscription = KISOverseasSubscription(
        code="AMD",
        market=KISOverseasMarket.NASDAQ,
        tr_id=KISOverseasTrId.TRADE,
    )

    assert subscription.to_websocket_subscription().tr_key == "DNASAMD"


def test_amex_orderbook_subscription_builds_kis_tr_key() -> None:
    subscription = KISOverseasSubscription(
        code="SPY",
        market=KISOverseasMarket.AMEX,
        tr_id=KISOverseasTrId.ORDERBOOK,
    )

    assert subscription.to_websocket_subscription() == KISWebSocketSubscription(
        tr_id="HDFSASP0",
        tr_key="DAMSSPY",
    )


def test_overseas_subscription_is_hashable() -> None:
    subscription = KISOverseasSubscription(
        code="NVDA",
        market=KISOverseasMarket.NASDAQ,
        tr_id=KISOverseasTrId.TRADE,
    )

    assert {subscription} == {subscription}


def test_overseas_trade_parses_all_typed_values() -> None:
    trade = KISOverseasTrade.from_body(_body_fields(GOOGL_TRADE_FRAMES[0]))

    assert trade.realtime_symbol == "DNASGOOGL"
    assert trade.symbol == "GOOGL"
    assert trade.decimal_places == 4
    assert trade.local_business_date == date(2026, 7, 10)
    assert trade.local_date == date(2026, 7, 10)
    assert trade.local_time == time(10, 43, 30)
    assert trade.korea_date == date(2026, 7, 10)
    assert trade.korea_time == time(23, 43, 30)
    assert trade.last_price == Decimal("354.4200")
    assert trade.trade_volume == 201
    assert trade.total_volume == 3474974
    assert trade.total_amount == Decimal("1237049112")
    assert trade.trade_strength == Decimal("46.09")


def test_overseas_trade_rejects_wrong_field_count() -> None:
    fields = _body_fields(GOOGL_TRADE_FRAMES[0])[:-1]

    with pytest.raises(ValueError, match="26"):
        KISOverseasTrade.from_body(fields)


def test_overseas_orderbook_groups_ten_levels_and_parses_metadata() -> None:
    orderbook = KISOverseasOrderbook.from_body(_body_fields(SPY_ORDERBOOK_FRAMES[0]))

    assert orderbook.realtime_symbol == "DAMSSPY"
    assert orderbook.symbol == "SPY"
    assert orderbook.decimal_places == 4
    assert orderbook.local_date == date(2026, 7, 10)
    assert orderbook.local_time == time(10, 53, 34)
    assert orderbook.korea_date == date(2026, 7, 10)
    assert orderbook.korea_time == time(23, 53, 34)
    assert orderbook.total_bid_quantity == 1621
    assert orderbook.total_ask_quantity == 1950
    assert orderbook.total_bid_quantity_change == -1200
    assert orderbook.total_ask_quantity_change == -735
    assert len(orderbook.levels) == 10
    assert orderbook.levels[0].bid_price == Decimal("752.1400")
    assert orderbook.levels[0].ask_price == Decimal("752.1700")
    assert orderbook.levels[0].bid_quantity == 60
    assert orderbook.levels[0].ask_quantity == 145
    assert orderbook.levels[0].bid_quantity_change == 35
    assert orderbook.levels[0].ask_quantity_change == 60
    assert orderbook.levels[9].bid_price == Decimal("752.0500")
    assert orderbook.levels[9].ask_price == Decimal("752.2600")
    assert orderbook.levels[9].bid_quantity == 100
    assert orderbook.levels[9].ask_quantity == 260
    assert orderbook.levels[9].bid_quantity_change == 0
    assert orderbook.levels[9].ask_quantity_change == 220


def test_overseas_orderbook_rejects_wrong_field_count() -> None:
    fields = _body_fields(SPY_ORDERBOOK_FRAMES[0])[:-1]

    with pytest.raises(ValueError, match="71"):
        KISOverseasOrderbook.from_body(fields)


@pytest.mark.parametrize(
    "message",
    [SUBSCRIBE_SUCCESS_ORDERBOOK, SUBSCRIBE_SUCCESS_TRADE],
)
def test_parse_frame_ignores_json_control_messages(message: str) -> None:
    assert parse_frame(message) is None


@pytest.mark.parametrize("frame", GOOGL_TRADE_FRAMES + SPY_TRADE_FRAMES)
def test_parse_frame_parses_trade_fixture(frame: str) -> None:
    parsed = parse_frame(frame)

    assert parsed is not None
    assert len(parsed) == 1
    assert isinstance(parsed[0], KISOverseasTrade)


@pytest.mark.parametrize("frame", SPY_ORDERBOOK_FRAMES)
def test_parse_frame_parses_orderbook_fixture(frame: str) -> None:
    parsed = parse_frame(frame)

    assert parsed is not None
    assert len(parsed) == 1
    assert isinstance(parsed[0], KISOverseasOrderbook)


def test_parse_frame_splits_multiple_trade_records() -> None:
    bodies = [frame.split("|", 3)[3] for frame in GOOGL_TRADE_FRAMES]
    frame = f"0|HDFSCNT0|003|{'^'.join(bodies)}"

    parsed = parse_frame(frame)

    assert parsed is not None
    assert [trade.total_volume for trade in parsed] == [3474974, 3474975, 3475208]


@pytest.mark.parametrize(
    ("frame", "message"),
    [
        ("0|UNKNOWN|001|value", "Unsupported"),
        ("0|HDFSCNT0|abc|value", "record count"),
        ("0|HDFSCNT0|000|value", "positive"),
        ("0|HDFSCNT0|001|value", "26"),
        ("0|HDFSASP0|001|value", "71"),
    ],
)
def test_parse_frame_rejects_malformed_data_frames(frame: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_frame(frame)


def test_overseas_package_reexports_websocket_dtos_and_parser() -> None:
    assert overseas_package.KISOverseasTrade is KISOverseasTrade
    assert overseas_package.KISOverseasOrderbook is KISOverseasOrderbook
    assert overseas_package.KISOverseasOrderbookLevel is KISOverseasOrderbookLevel
    assert overseas_package.parse_frame is parse_frame

from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.engine.default import DefaultDialect
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.models import UTCDateTime
from app.kis.overseas.models import OverseasOrderbook, OverseasTrade
from app.kis.overseas.repository import (
    KISOverseasTickRepository,
    to_orderbook_row,
    to_trade_row,
)
from app.kis.overseas.schemas import KISOverseasOrderbook, KISOverseasTrade
from tests.kis.overseas.fixtures import GOOGL_TRADE_FRAMES, SPY_ORDERBOOK_FRAMES


def _body_fields(frame: str) -> list[str]:
    """웹소켓 fixture에서 본문 필드만 분리한다."""

    return frame.split("|", 3)[3].split("^")


def test_to_trade_row_maps_overseas_trade_and_market() -> None:
    trade = KISOverseasTrade.from_body(_body_fields(GOOGL_TRADE_FRAMES[0]))
    received_at = datetime(2026, 7, 10, 14, 44, tzinfo=UTC)

    row = to_trade_row(trade, received_at)

    assert row.realtime_symbol == "DNASGOOGL"
    assert row.symbol == "GOOGL"
    assert row.market == "NAS"
    assert row.event_ts == datetime(2026, 7, 10, 14, 43, 30, tzinfo=UTC)
    assert row.local_business_date == trade.local_business_date
    assert row.price == trade.last_price
    assert row.volume == 201
    assert row.received_at == received_at
    assert row.details["local_time"] == "10:43:30"
    assert row.details["korea_time"] == "23:43:30"
    assert "last_price" not in row.details


def test_to_orderbook_row_maps_overseas_best_level_and_market() -> None:
    orderbook = KISOverseasOrderbook.from_body(_body_fields(SPY_ORDERBOOK_FRAMES[0]))
    received_at = datetime(2026, 7, 10, 14, 54, tzinfo=UTC)

    row = to_orderbook_row(orderbook, received_at)

    assert row.realtime_symbol == "DAMSSPY"
    assert row.symbol == "SPY"
    assert row.market == "AMS"
    assert row.event_ts == datetime(2026, 7, 10, 14, 53, 34, tzinfo=UTC)
    assert row.best_bid_price == orderbook.levels[0].bid_price
    assert row.best_ask_price == orderbook.levels[0].ask_price
    assert row.levels[0]["bid_price"] == "752.1400"
    assert row.received_at == received_at
    assert row.details["local_time"] == "10:53:34"
    assert "levels" not in row.details


def test_received_at_validation_is_deferred_to_utc_column_type() -> None:
    orderbook = KISOverseasOrderbook.from_body(_body_fields(SPY_ORDERBOOK_FRAMES[0]))
    received_at = datetime(2026, 7, 10, 14, 54)

    row = to_orderbook_row(orderbook, received_at)

    assert row.received_at == received_at
    column_type = OverseasOrderbook.__table__.c.received_at.type
    assert isinstance(column_type, UTCDateTime)
    with pytest.raises(ValueError, match="timezone-aware"):
        column_type.process_bind_param(row.received_at, DefaultDialect())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("event", "expected_model"),
    [
        (
            KISOverseasTrade.from_body(_body_fields(GOOGL_TRADE_FRAMES[0])),
            OverseasTrade,
        ),
        (
            KISOverseasOrderbook.from_body(_body_fields(SPY_ORDERBOOK_FRAMES[0])),
            OverseasOrderbook,
        ),
    ],
)
async def test_repository_saves_each_tick_in_its_own_transaction(
    event: KISOverseasTrade | KISOverseasOrderbook,
    expected_model: type[OverseasTrade] | type[OverseasOrderbook],
) -> None:
    session = MagicMock(spec=AsyncSession)
    transaction = AsyncMock()
    transaction.__aenter__.return_value = session
    session_factory = MagicMock(spec=async_sessionmaker)
    session_factory.begin.return_value = transaction
    repository = KISOverseasTickRepository(cast("async_sessionmaker[AsyncSession]", session_factory))

    await repository.save(event, datetime(2026, 7, 10, 14, 54, tzinfo=UTC))

    saved_row = session.add.call_args.args[0]
    assert isinstance(saved_row, expected_model)
    transaction.__aenter__.assert_awaited_once()
    transaction.__aexit__.assert_awaited_once()

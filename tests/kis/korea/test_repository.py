from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.engine.default import DefaultDialect
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.models import UTCDateTime
from app.kis.korea.models import KoreaOrderbook, KoreaTrade
from app.kis.korea.repository import KISKoreaTickRepository, to_orderbook_row, to_trade_row
from app.kis.korea.schemas import KISKoreaOrderbook, KISKoreaTrade
from tests.kis.korea.fixtures import SK_HYNIX_ORDERBOOK_FRAMES, SK_HYNIX_TRADE_FRAMES


def _body_fields(frame: str) -> list[str]:
    """웹소켓 fixture에서 본문 필드만 분리한다."""

    return frame.split("|", 3)[3].split("^")


def test_to_trade_row_maps_korea_trade_and_utc_times() -> None:
    trade = KISKoreaTrade.from_body(_body_fields(SK_HYNIX_TRADE_FRAMES[0]))
    received_at = datetime(2026, 7, 13, 1, 40, tzinfo=UTC)

    row = to_trade_row(trade, received_at)

    assert row.stock_code == "000660"
    assert row.event_ts == datetime(2026, 7, 13, 1, 39, 25, tzinfo=UTC)
    assert row.price == trade.current_price
    assert row.volume == 20
    assert row.cumulative_volume == 2388396
    assert row.received_at == received_at
    assert row.details["business_date"] == "2026-07-13"
    assert row.details["trade_time"] == "10:39:25"
    assert "current_price" not in row.details


def test_to_orderbook_row_maps_first_level_and_received_date() -> None:
    orderbook = KISKoreaOrderbook.from_body(_body_fields(SK_HYNIX_ORDERBOOK_FRAMES[0]))
    received_at = datetime(2026, 7, 13, 1, 40, tzinfo=UTC)

    row = to_orderbook_row(orderbook, received_at)

    assert row.stock_code == "000660"
    assert row.event_ts == datetime(2026, 7, 13, 1, 39, 25, tzinfo=UTC)
    assert row.best_ask_price == orderbook.levels[0].ask_price
    assert row.best_bid_price == orderbook.levels[0].bid_price
    assert row.levels[0]["ask_price"] == "1996000"
    assert row.received_at == received_at
    assert row.details["business_time"] == "10:39:25"
    assert "levels" not in row.details


def test_received_at_validation_is_deferred_to_utc_column_type() -> None:
    trade = KISKoreaTrade.from_body(_body_fields(SK_HYNIX_TRADE_FRAMES[0]))
    received_at = datetime(2026, 7, 13, 1, 40)

    row = to_trade_row(trade, received_at)

    assert row.received_at == received_at
    column_type = KoreaTrade.__table__.c.received_at.type
    assert isinstance(column_type, UTCDateTime)
    with pytest.raises(ValueError, match="timezone-aware"):
        column_type.process_bind_param(row.received_at, DefaultDialect())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("event", "expected_model"),
    [
        (
            KISKoreaTrade.from_body(_body_fields(SK_HYNIX_TRADE_FRAMES[0])),
            KoreaTrade,
        ),
        (
            KISKoreaOrderbook.from_body(_body_fields(SK_HYNIX_ORDERBOOK_FRAMES[0])),
            KoreaOrderbook,
        ),
    ],
)
async def test_repository_saves_each_tick_in_its_own_transaction(
    event: KISKoreaTrade | KISKoreaOrderbook,
    expected_model: type[KoreaTrade] | type[KoreaOrderbook],
) -> None:
    session = MagicMock(spec=AsyncSession)
    transaction = AsyncMock()
    transaction.__aenter__.return_value = session
    session_factory = MagicMock(spec=async_sessionmaker)
    session_factory.begin.return_value = transaction
    repository = KISKoreaTickRepository(cast("async_sessionmaker[AsyncSession]", session_factory))

    await repository.save(event, datetime(2026, 7, 13, 1, 40, tzinfo=UTC))

    saved_row = session.add.call_args.args[0]
    assert isinstance(saved_row, expected_model)
    transaction.__aenter__.assert_awaited_once()
    transaction.__aexit__.assert_awaited_once()

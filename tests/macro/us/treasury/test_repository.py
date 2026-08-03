from datetime import UTC, date, datetime
from decimal import Decimal
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import Insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.macro.us.treasury.repository import UsTreasuryYieldRepository
from app.macro.us.treasury.schemas import (
    IntradayBar,
    TreasuryFinalObservation,
    TreasuryIntradayResult,
    TreasurySeries,
)


SNAPSHOT_TS = datetime(2026, 7, 28, 5, 30, tzinfo=UTC)

BARS = (
    IntradayBar(
        event_ts=datetime(2026, 7, 28, 4, 0, tzinfo=UTC),
        open=Decimal("108.65625"),
        high=Decimal("108.65625"),
        low=Decimal("108.65625"),
        close=Decimal("108.65625"),
    ),
    IntradayBar(
        event_ts=datetime(2026, 7, 28, 4, 1, tzinfo=UTC),
        open=None,
        high=None,
        low=None,
        close=Decimal("108.671875"),
    ),
)


def _session_factory(rowcount: int) -> tuple[MagicMock, AsyncMock]:
    """execute의 rowcount를 고정한 세션 팩토리 mock을 만든다.

    Args:
        rowcount: execute가 돌려줄 삽입 행 수.

    Returns:
        세션 팩토리 mock과 세션 mock.
    """

    execute_result = MagicMock()
    execute_result.rowcount = rowcount
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = execute_result
    session_context = AsyncMock()
    session_context.__aenter__.return_value = session
    session_factory = MagicMock(spec=async_sessionmaker)
    session_factory.begin.return_value = session_context
    return session_factory, session


def _compiled(statement: object) -> str:
    assert isinstance(statement, Insert)
    return str(statement.compile(dialect=postgresql.dialect()))


@pytest.mark.asyncio
async def test_save_intraday_inserts_one_statement_with_on_conflict_do_nothing() -> None:
    session_factory, session = _session_factory(rowcount=2)
    repository = UsTreasuryYieldRepository(cast("async_sessionmaker[AsyncSession]", session_factory))
    result = TreasuryIntradayResult(series=TreasurySeries.ZN_FUTURE, bars=BARS)

    saved = await repository.save_intraday(result, SNAPSHOT_TS)

    assert saved == 2
    session.execute.assert_awaited_once()
    statement = session.execute.await_args.args[0]
    compiled = _compiled(statement)
    assert "INSERT INTO us_treasury_bars" in compiled
    assert "ON CONFLICT ON CONSTRAINT uq_us_treasury_bars_series_event_ts DO NOTHING" in compiled
    # 다중 VALUES 단일 문장이어야 rowcount를 신뢰할 수 있다.
    assert compiled.count("VALUES") == 1
    assert compiled.count("%(series_m0)s") == 1
    assert compiled.count("%(series_m1)s") == 1


@pytest.mark.asyncio
async def test_save_intraday_maps_every_bar_column() -> None:
    session_factory, session = _session_factory(rowcount=2)
    repository = UsTreasuryYieldRepository(cast("async_sessionmaker[AsyncSession]", session_factory))
    result = TreasuryIntradayResult(series=TreasurySeries.ZN_FUTURE, bars=BARS)

    await repository.save_intraday(result, SNAPSHOT_TS)

    statement = session.execute.await_args.args[0]
    assert isinstance(statement, Insert)
    rows = statement.compile(dialect=postgresql.dialect()).params
    assert rows["series_m0"] == TreasurySeries.ZN_FUTURE
    assert rows["event_ts_m0"] == datetime(2026, 7, 28, 4, 0, tzinfo=UTC)
    assert rows["open_m0"] == Decimal("108.65625")
    assert rows["high_m0"] == Decimal("108.65625")
    assert rows["low_m0"] == Decimal("108.65625")
    assert rows["close_m0"] == Decimal("108.65625")
    assert rows["snapshot_ts_m0"] == SNAPSHOT_TS
    assert rows["open_m1"] is None
    assert rows["close_m1"] == Decimal("108.671875")


@pytest.mark.asyncio
async def test_save_intraday_skips_the_database_when_no_bars_arrived() -> None:
    session_factory, session = _session_factory(rowcount=0)
    repository = UsTreasuryYieldRepository(cast("async_sessionmaker[AsyncSession]", session_factory))
    result = TreasuryIntradayResult(series=TreasurySeries.US_10Y, bars=())

    saved = await repository.save_intraday(result, SNAPSHOT_TS)

    assert saved == 0
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_save_intraday_returns_rowcount_when_bars_are_duplicates() -> None:
    # 폐장 후 폴링은 직전 세션 봉을 다시 받는다. 전부 skip되어 0이어야 한다.
    session_factory, _ = _session_factory(rowcount=0)
    repository = UsTreasuryYieldRepository(cast("async_sessionmaker[AsyncSession]", session_factory))
    result = TreasuryIntradayResult(series=TreasurySeries.US_10Y, bars=BARS)

    assert await repository.save_intraday(result, SNAPSHOT_TS) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("rowcount", [0, 1])
async def test_save_final_inserts_with_on_conflict_do_nothing(rowcount: int) -> None:
    session_factory, session = _session_factory(rowcount=rowcount)
    repository = UsTreasuryYieldRepository(cast("async_sessionmaker[AsyncSession]", session_factory))
    observation = TreasuryFinalObservation(
        series=TreasurySeries.US_10Y,
        observation_date=date(2026, 7, 24),
        yield_pct=Decimal("4.64"),
    )

    saved = await repository.save_final([observation], SNAPSHOT_TS)

    assert saved == rowcount
    statement = session.execute.await_args.args[0]
    compiled = _compiled(statement)
    assert "INSERT INTO us_treasury_yield_daily" in compiled
    assert "ON CONFLICT ON CONSTRAINT uq_us_treasury_yield_daily_series_observation_date DO NOTHING" in compiled
    assert isinstance(statement, Insert)
    params = statement.compile(dialect=postgresql.dialect()).params
    assert params["series_m0"] == TreasurySeries.US_10Y
    assert params["observation_date_m0"] == date(2026, 7, 24)
    assert params["yield_pct_m0"] == Decimal("4.64")
    assert params["snapshot_ts_m0"] == SNAPSHOT_TS


@pytest.mark.asyncio
async def test_save_final_inserts_backfill_range_in_one_statement() -> None:
    session_factory, session = _session_factory(rowcount=2)
    repository = UsTreasuryYieldRepository(cast("async_sessionmaker[AsyncSession]", session_factory))
    observations = [
        TreasuryFinalObservation(
            series=TreasurySeries.US_10Y,
            observation_date=date(2025, 1, 2),
            yield_pct=Decimal("4.56"),
        ),
        TreasuryFinalObservation(
            series=TreasurySeries.US_10Y,
            observation_date=date(2025, 1, 3),
            yield_pct=Decimal("4.60"),
        ),
    ]

    assert await repository.save_final(observations, SNAPSHOT_TS) == 2

    params = session.execute.await_args.args[0].compile(dialect=postgresql.dialect()).params
    assert params["observation_date_m0"] == date(2025, 1, 2)
    assert params["observation_date_m1"] == date(2025, 1, 3)


@pytest.mark.asyncio
async def test_save_final_without_observations_does_not_insert() -> None:
    session_factory, session = _session_factory(rowcount=0)
    repository = UsTreasuryYieldRepository(cast("async_sessionmaker[AsyncSession]", session_factory))

    assert await repository.save_final([], SNAPSHOT_TS) == 0
    session.execute.assert_not_awaited()

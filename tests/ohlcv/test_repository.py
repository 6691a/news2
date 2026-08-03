from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import Insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.instruments.models import Market
from app.ohlcv.repository import OhlcvRepository
from app.ohlcv.schemas import DailyBar, DailyBarsResult


SNAPSHOT_TS = datetime(2026, 7, 31, 9, 0, tzinfo=UTC)

BARS = (
    DailyBar(
        event_ts=datetime(2026, 7, 28, 15, 0, tzinfo=UTC),
        open=Decimal("75000"),
        high=Decimal("75900"),
        low=Decimal("74800"),
        close=Decimal("75600"),
        volume=9876543,
    ),
    DailyBar(
        event_ts=datetime(2026, 7, 29, 15, 0, tzinfo=UTC),
        open=Decimal("76100"),
        high=Decimal("77000"),
        low=Decimal("75900"),
        close=Decimal("76800"),
        volume=12345678,
    ),
)


def _session_factory(
    instruments: list[tuple[str, Market, int]],
    rowcount: int,
) -> tuple[MagicMock, AsyncMock]:
    """종목 조회 결과와 삽입 rowcount를 고정한 세션 팩토리 mock을 만든다.

    Args:
        instruments: 종목 조회가 돌려줄 (ticker, market, id) 행 목록.
        rowcount: 삽입 문장이 돌려줄 영향 행 수.

    Returns:
        세션 팩토리 mock과 세션 mock.
    """

    select_result = MagicMock()
    select_result.all.return_value = instruments
    insert_result = MagicMock()
    insert_result.rowcount = rowcount

    session = AsyncMock(spec=AsyncSession)
    session.execute.side_effect = [select_result, insert_result]
    session_context = AsyncMock()
    session_context.__aenter__.return_value = session
    session_factory = MagicMock(spec=async_sessionmaker)
    session_factory.begin.return_value = session_context
    return session_factory, session


def _repository(session_factory: MagicMock) -> OhlcvRepository:
    return OhlcvRepository(cast("async_sessionmaker[AsyncSession]", session_factory))


def _compiled(statement: object) -> str:
    assert isinstance(statement, Insert)
    return str(statement.compile(dialect=postgresql.dialect()))


@pytest.mark.asyncio
async def test_save_daily_upserts_only_when_close_changed() -> None:
    session_factory, session = _session_factory([("005930", Market.KRX, 1)], rowcount=2)
    result = DailyBarsResult(ticker="005930", market=Market.KRX, bars=BARS)

    saved = await _repository(session_factory).save_daily([result], SNAPSHOT_TS)

    assert saved == 2
    statement = _compiled(session.execute.await_args_list[1].args[0])
    assert "ON CONFLICT ON CONSTRAINT uq_ohlcv_instrument_timeframe_ts DO UPDATE" in statement
    assert "WHERE ohlcv.close IS DISTINCT FROM excluded.close" in statement
    # 단일 VALUES 문장이어야 rowcount를 신뢰할 수 있다.
    assert statement.count("SET") == 1


@pytest.mark.asyncio
async def test_save_daily_skips_unregistered_instrument() -> None:
    session_factory, session = _session_factory([("005930", Market.KRX, 1)], rowcount=0)
    result = DailyBarsResult(ticker="TSLA", market=Market.NASDAQ, bars=BARS)

    saved = await _repository(session_factory).save_daily([result], SNAPSHOT_TS)

    assert saved == 0
    # 저장할 행이 없으면 삽입 문장을 만들지 않는다(종목 조회 1회만).
    assert session.execute.await_count == 1


@pytest.mark.asyncio
async def test_save_daily_deduplicates_same_bar_key() -> None:
    session_factory, session = _session_factory([("005930", Market.KRX, 1)], rowcount=2)
    duplicated = DailyBarsResult(ticker="005930", market=Market.KRX, bars=(*BARS, BARS[0]))

    await _repository(session_factory).save_daily([duplicated], SNAPSHOT_TS)

    statement = session.execute.await_args_list[1].args[0]
    assert isinstance(statement, Insert)
    # VALUES 행마다 파라미터에 _m<행번호> 접미사가 붙는다. 겹친 행이 빠져 두 행만 남아야 한다.
    parameters = statement.compile(dialect=postgresql.dialect()).params
    assert any(key.endswith("_m1") for key in parameters)
    assert not any(key.endswith("_m2") for key in parameters)


@pytest.mark.asyncio
async def test_save_daily_without_bars_does_not_insert() -> None:
    session_factory, session = _session_factory([("005930", Market.KRX, 1)], rowcount=0)
    empty = DailyBarsResult(ticker="005930", market=Market.KRX, bars=())

    assert await _repository(session_factory).save_daily([empty], SNAPSHOT_TS) == 0
    assert session.execute.await_count == 1

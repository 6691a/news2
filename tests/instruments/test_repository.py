"""Instrument repository 테스트."""

from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.instruments.models import Instrument, Market
from app.instruments.repository import InstrumentRepository


@pytest.mark.asyncio
async def test_list_watched_returns_only_watched_instruments_in_id_order() -> None:
    watched = [
        Instrument(ticker="005930", market=Market.KRX, name="삼성전자"),
        Instrument(ticker="AAPL", market=Market.NASDAQ, name="Apple"),
    ]
    scalar_result = MagicMock()
    scalar_result.all.return_value = watched
    session = AsyncMock(spec=AsyncSession)
    session.scalars.return_value = scalar_result
    session_context = AsyncMock()
    session_context.__aenter__.return_value = session
    session_factory = MagicMock(spec=async_sessionmaker)
    session_factory.return_value = session_context
    repository = InstrumentRepository(cast("async_sessionmaker[AsyncSession]", session_factory))

    result = await repository.list_watched()

    assert result == watched
    statement = session.scalars.await_args.args[0]
    sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "WHERE instruments.is_watched IS true" in sql
    assert "ORDER BY instruments.id" in sql
    session_context.__aenter__.assert_awaited_once()
    session_context.__aexit__.assert_awaited_once()

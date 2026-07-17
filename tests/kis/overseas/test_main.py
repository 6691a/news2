from collections.abc import AsyncIterator
from datetime import datetime

import pytest
from dependency_injector import providers
from sqlalchemy.exc import SQLAlchemyError

from app.core.containers import container
from app.instruments.models import Instrument, Market
from app.kis.overseas.__main__ import main
from app.kis.overseas.schemas import (
    KISOverseasMarket,
    KISOverseasOrderbook,
    KISOverseasStockCode,
    KISOverseasSubscription,
    KISOverseasTrade,
    KISOverseasTrId,
    parse_frame,
)
from tests.kis.overseas.fixtures import GOOGL_TRADE_FRAMES


class FakeDatabase:
    """메인 프로세스의 DB 풀 종료 여부를 기록한다."""

    def __init__(self) -> None:
        self.disposed = False

    async def dispose(self) -> None:
        """DB 풀 종료 호출을 기록한다."""

        self.disposed = True


class FakeRepository:
    """첫 저장만 실패시키고 이후 호출을 기록한다."""

    def __init__(self) -> None:
        self.calls: list[tuple[KISOverseasTrade | KISOverseasOrderbook, datetime]] = []

    async def save(
        self,
        event: KISOverseasTrade | KISOverseasOrderbook,
        received_at: datetime,
    ) -> None:
        """호출을 기록하고 첫 저장에서 DB 오류를 발생시킨다."""

        self.calls.append((event, received_at))
        if len(self.calls) == 1:
            raise SQLAlchemyError("database unavailable")


class FakeInstrumentRepository:
    """테스트용 추적 종목 목록을 반환한다."""

    async def list_watched(self) -> list[Instrument]:
        """해외 두 종목과 필터링할 국내 한 종목을 반환한다."""

        return [
            Instrument(ticker="005930", market=Market.KRX, name="삼성전자"),
            Instrument(ticker="GOOGL", market=Market.NASDAQ, name="Alphabet"),
            Instrument(ticker="SPY", market=Market.NYSE_ARCA, name="SPDR S&P 500 ETF"),
        ]


@pytest.mark.asyncio
async def test_main_continues_after_tick_save_failure_and_disposes_database() -> None:
    events: list[KISOverseasTrade | KISOverseasOrderbook] = []
    subscriptions: list[KISOverseasSubscription] = []
    for frame in GOOGL_TRADE_FRAMES[:2]:
        parsed = parse_frame(frame)
        assert parsed is not None
        events.append(parsed[0])
    repository = FakeRepository()
    database = FakeDatabase()

    class FakeQuote:
        async def subscribe(self, subscription: KISOverseasSubscription) -> None:
            subscriptions.append(subscription)

        async def run(self) -> None:
            return None

        async def stream(self) -> AsyncIterator[KISOverseasTrade | KISOverseasOrderbook]:
            for event in events:
                yield event

    with (
        container.overseas_websocket_quote.override(providers.Object(FakeQuote())),
        container.overseas_tick_repository.override(providers.Object(repository)),
        container.instrument_repository.override(providers.Object(FakeInstrumentRepository())),
        container.database.override(providers.Object(database)),
    ):
        await main()

    assert [event for event, _ in repository.calls] == events
    assert {(subscription.code, subscription.market, subscription.tr_id) for subscription in subscriptions} == {
        (KISOverseasStockCode.ALPHABET, KISOverseasMarket.NASDAQ, KISOverseasTrId.TRADE),
        (KISOverseasStockCode.ALPHABET, KISOverseasMarket.NASDAQ, KISOverseasTrId.ORDERBOOK),
        (KISOverseasStockCode.SP500, KISOverseasMarket.AMEX, KISOverseasTrId.TRADE),
        (KISOverseasStockCode.SP500, KISOverseasMarket.AMEX, KISOverseasTrId.ORDERBOOK),
    }
    assert all(received_at.utcoffset() is not None for _, received_at in repository.calls)
    assert database.disposed is True

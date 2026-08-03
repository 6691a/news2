from collections.abc import AsyncIterator
from datetime import datetime

import pytest
from dependency_injector import providers
from sqlalchemy.exc import SQLAlchemyError
from structlog.testing import capture_logs

from app.core.containers import container
from app.instruments.models import Instrument, InstrumentKind, Market
from app.kis.overseas.__main__ import main
from app.kis.overseas.schemas import (
    KISOverseasMarket,
    KISOverseasOrderbook,
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
        """구독 대상 세 종목과 걸러내야 할 국내·지수 종목을 반환한다."""

        return [
            Instrument(ticker="005930", market=Market.KRX, name="삼성전자", kind=InstrumentKind.EQUITY),
            Instrument(ticker="GOOGL", market=Market.NASDAQ, name="Alphabet", kind=InstrumentKind.EQUITY),
            Instrument(ticker="SPY", market=Market.NYSE_ARCA, name="SPDR S&P 500 ETF", kind=InstrumentKind.ETF),
            # NYSE 매핑이 빠져 있어 조용히 누락되던 종목이다.
            Instrument(ticker="TSM", market=Market.NYSE, name="TSMC ADR", kind=InstrumentKind.EQUITY),
            # 미국 지수는 KIS 해외주식 실시간 대상이 아니다.
            Instrument(ticker="^GSPC", market=Market.US_INDEX, name="S&P 500", kind=InstrumentKind.INDEX),
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
        ("GOOGL", KISOverseasMarket.NASDAQ, KISOverseasTrId.TRADE),
        ("GOOGL", KISOverseasMarket.NASDAQ, KISOverseasTrId.ORDERBOOK),
        ("SPY", KISOverseasMarket.AMEX, KISOverseasTrId.TRADE),
        ("SPY", KISOverseasMarket.AMEX, KISOverseasTrId.ORDERBOOK),
        ("TSM", KISOverseasMarket.NYSE, KISOverseasTrId.TRADE),
        ("TSM", KISOverseasMarket.NYSE, KISOverseasTrId.ORDERBOOK),
    }
    assert all(received_at.utcoffset() is not None for _, received_at in repository.calls)
    assert database.disposed is True


@pytest.mark.asyncio
async def test_main_reports_subscribed_and_skipped_instruments() -> None:
    subscriptions: list[KISOverseasSubscription] = []
    database = FakeDatabase()

    class SilentQuote:
        async def subscribe(self, subscription: KISOverseasSubscription) -> None:
            subscriptions.append(subscription)

        async def run(self) -> None:
            return None

        async def stream(self) -> AsyncIterator[KISOverseasTrade | KISOverseasOrderbook]:
            return
            yield  # pragma: no cover - 빈 스트림을 만들기 위한 자리다

    with (
        container.overseas_websocket_quote.override(providers.Object(SilentQuote())),
        container.overseas_tick_repository.override(providers.Object(FakeRepository())),
        container.instrument_repository.override(providers.Object(FakeInstrumentRepository())),
        container.database.override(providers.Object(database)),
        capture_logs() as logs,
    ):
        await main()

    ready = [entry for entry in logs if entry["event"] == "kis_tick_subscriptions_ready"]
    assert len(ready) == 1
    # 종목 5개 중 3개 구독(GOOGL·SPY·TSM), 2개 제외(국내·미국 지수).
    assert (ready[0]["watched"], ready[0]["subscribed"], ready[0]["skipped"]) == (5, 3, 2)

    # 매핑을 빠뜨려도 제외와 같은 모양이라 건너뛴 대상을 하나씩 남긴다.
    skipped = [entry for entry in logs if entry["event"] == "kis_tick_market_not_subscribable"]
    assert {entry["ticker"] for entry in skipped} == {"005930", "^GSPC"}
    assert {entry["instrument_market"] for entry in skipped} == {"KRX", "US_INDEX"}

from collections.abc import AsyncIterator
from datetime import datetime

import pytest
from dependency_injector import providers
from sqlalchemy.exc import SQLAlchemyError
from structlog.testing import capture_logs

from app.core.containers import container
from app.instruments.models import Instrument, InstrumentKind, Market
from app.kis.korea.__main__ import main
from app.kis.korea.schemas import (
    KISKoreaOrderbook,
    KISKoreaSubscription,
    KISKoreaTrade,
    KISKoreaTrId,
    parse_frame,
)
from tests.kis.korea.fixtures import SK_HYNIX_TRADE_FRAMES


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
        self.calls: list[tuple[KISKoreaTrade | KISKoreaOrderbook, datetime]] = []

    async def save(
        self,
        event: KISKoreaTrade | KISKoreaOrderbook,
        received_at: datetime,
    ) -> None:
        """호출을 기록하고 첫 저장에서 DB 오류를 발생시킨다."""

        self.calls.append((event, received_at))
        if len(self.calls) == 1:
            raise SQLAlchemyError("database unavailable")


class FakeInstrumentRepository:
    """테스트용 추적 종목 목록을 반환한다."""

    async def list_watched(self) -> list[Instrument]:
        """국내 두 종목과 걸러내야 할 해외 종목·국내 지수를 반환한다."""

        return [
            Instrument(ticker="005930", market=Market.KRX, name="삼성전자", kind=InstrumentKind.EQUITY),
            Instrument(ticker="000660", market=Market.KRX, name="SK하이닉스", kind=InstrumentKind.EQUITY),
            Instrument(ticker="AAPL", market=Market.NASDAQ, name="Apple", kind=InstrumentKind.EQUITY),
            # KOSPI는 시장이 KRX여도 체결가가 없어 실시간 TR로 구독하면 KIS가 거절한다.
            Instrument(ticker="KOSPI", market=Market.KRX, name="코스피", kind=InstrumentKind.INDEX),
        ]


@pytest.mark.asyncio
async def test_main_skips_index_instruments_and_reports_subscription_counts() -> None:
    subscriptions: list[KISKoreaSubscription] = []
    database = FakeDatabase()

    class SilentQuote:
        async def subscribe(self, subscription: KISKoreaSubscription) -> None:
            subscriptions.append(subscription)

        async def run(self) -> None:
            return None

        async def stream(self) -> AsyncIterator[KISKoreaTrade | KISKoreaOrderbook]:
            return
            yield  # pragma: no cover - 빈 스트림을 만들기 위한 자리다

    with (
        container.korea_websocket_quote.override(providers.Object(SilentQuote())),
        container.korea_tick_repository.override(providers.Object(FakeRepository())),
        container.instrument_repository.override(providers.Object(FakeInstrumentRepository())),
        container.database.override(providers.Object(database)),
        capture_logs() as logs,
    ):
        await main()

    # 지수는 체결가가 없어 구독하면 KIS가 거절하고 프로세스가 죽는다.
    assert "KOSPI" not in {subscription.code for subscription in subscriptions}
    ready = [entry for entry in logs if entry["event"] == "kis_tick_subscriptions_ready"]
    assert len(ready) == 1
    # 종목 4개 중 2개 구독, 2개 제외(해외 1 + 국내 지수 1).
    assert (ready[0]["watched"], ready[0]["subscribed"], ready[0]["skipped"]) == (4, 2, 2)


@pytest.mark.asyncio
async def test_main_continues_after_tick_save_failure_and_disposes_database() -> None:
    events: list[KISKoreaTrade | KISKoreaOrderbook] = []
    subscriptions: list[KISKoreaSubscription] = []
    for frame in SK_HYNIX_TRADE_FRAMES[:2]:
        parsed = parse_frame(frame)
        assert parsed is not None
        events.append(parsed[0])
    repository = FakeRepository()
    database = FakeDatabase()

    class FakeQuote:
        async def subscribe(self, subscription: KISKoreaSubscription) -> None:
            subscriptions.append(subscription)

        async def run(self) -> None:
            return None

        async def stream(self) -> AsyncIterator[KISKoreaTrade | KISKoreaOrderbook]:
            for event in events:
                yield event

    with (
        container.korea_websocket_quote.override(providers.Object(FakeQuote())),
        container.korea_tick_repository.override(providers.Object(repository)),
        container.instrument_repository.override(providers.Object(FakeInstrumentRepository())),
        container.database.override(providers.Object(database)),
    ):
        await main()

    assert [event for event, _ in repository.calls] == events
    assert {(subscription.code, subscription.tr_id) for subscription in subscriptions} == {
        ("005930", KISKoreaTrId.STOCK_TRADE_KRX),
        ("005930", KISKoreaTrId.STOCK_ORDERBOOK_KRX),
        ("000660", KISKoreaTrId.STOCK_TRADE_KRX),
        ("000660", KISKoreaTrId.STOCK_ORDERBOOK_KRX),
    }
    assert all(received_at.utcoffset() is not None for _, received_at in repository.calls)
    assert database.disposed is True

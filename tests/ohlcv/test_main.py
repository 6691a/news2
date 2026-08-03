import logging
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from dependency_injector import providers

from app.core.collection import BACKFILL_KEYWORD, BACKFILL_START
from app.core.containers import container
from app.instruments.models import Instrument, InstrumentKind, Market
from app.ohlcv.__main__ import _collect, build_options, main
from app.notifications.models import IssueKind
from tests.notifications.fakes import RecordingIssueCollector
from app.ohlcv.schemas import DailyBar, DailyBarsResult, OhlcvCollectOptions, OhlcvScope


def test_build_options_defaults_to_all_markets_recent_window() -> None:
    options = build_options([])

    assert options.scope is OhlcvScope.ALL
    assert options.start is None
    assert options.end is None


def test_build_options_reads_scope() -> None:
    assert build_options(["korea"]).scope is OhlcvScope.KOREA
    assert build_options(["overseas"]).scope is OhlcvScope.OVERSEAS


def test_build_options_reads_explicit_period() -> None:
    options = build_options(["overseas", "2024-01-01", "2026-07-31"])

    assert options.scope is OhlcvScope.OVERSEAS
    assert options.start == date(2024, 1, 1)
    assert options.end == date(2026, 7, 31)


def test_build_options_backfill_keyword_uses_baseline_start() -> None:
    options = build_options(["korea", BACKFILL_KEYWORD])

    assert options.scope is OhlcvScope.KOREA
    assert options.start == BACKFILL_START
    # 종료일은 시장별 오늘로 정해지므로 옵션에는 남기지 않는다.
    assert options.end is None


def test_build_options_start_only_runs_to_today() -> None:
    options = build_options(["2025-06-01"])

    assert options.start == date(2025, 6, 1)
    assert options.end is None


def test_build_options_accepts_period_without_scope() -> None:
    options = build_options(["2024-01-01", "2024-03-01"])

    assert options.scope is OhlcvScope.ALL
    assert options.start == date(2024, 1, 1)


def test_build_options_rejects_extra_arguments() -> None:
    with pytest.raises(ValueError, match="start and optional end"):
        build_options(["korea", "2024-01-01", "2024-02-01", "2024-03-01"])


class _FakeKoreaService:
    """국내 일봉 서비스 호출을 기록한다."""

    def __init__(self, bars: tuple[DailyBar, ...] = ()) -> None:
        self.calls: list[str] = []
        self._bars = bars

    async def collect_daily(self, ticker: str, start: date, end: date, client: object) -> DailyBarsResult:
        """호출한 티커를 기록하고 고정 결과를 돌려준다."""

        del start, end, client
        self.calls.append(ticker)
        return DailyBarsResult(ticker=ticker, market=Market.KRX, bars=self._bars)


class _FakeOverseasService:
    """해외·지수 일봉 서비스 호출을 기록한다."""

    def __init__(self, bars: tuple[DailyBar, ...] = ()) -> None:
        self.calls: list[tuple[str, str]] = []
        self._bars = bars

    async def collect_daily(
        self,
        ticker: str,
        market: Market,
        start: date,
        end: date,
        symbol: str | None = None,
    ) -> DailyBarsResult:
        """호출한 (티커, 심볼)을 기록하고 고정 결과를 돌려준다."""

        del start, end
        self.calls.append((ticker, symbol or ticker))
        return DailyBarsResult(ticker=ticker, market=market, bars=self._bars)


def _instrument(ticker: str, market: Market, kind: InstrumentKind, source_symbol: str | None = None) -> Instrument:
    return Instrument(ticker=ticker, market=market, name=ticker, kind=kind, source_symbol=source_symbol)


BAR = DailyBar(
    event_ts=datetime(2026, 7, 29, 15, 0, tzinfo=UTC),
    open=Decimal("1"),
    high=Decimal("1"),
    low=Decimal("1"),
    close=Decimal("1"),
    volume=0,
)


@pytest.mark.asyncio
async def test_collect_routes_korean_equity_to_kis() -> None:
    korea, overseas = _FakeKoreaService((BAR,)), _FakeOverseasService()

    await _collect(
        _instrument("005930", Market.KRX, InstrumentKind.EQUITY),
        date(2026, 7, 24),
        date(2026, 7, 31),
        korea,
        overseas,
        client=None,
    )

    assert korea.calls == ["005930"]
    assert overseas.calls == []


@pytest.mark.asyncio
async def test_collect_routes_korean_index_to_yahoo_with_source_symbol() -> None:
    korea, overseas = _FakeKoreaService(), _FakeOverseasService((BAR,))

    # KOSPI는 시장이 KRX여도 종목 시세 TR로 못 받는다. 소스 심볼로 Yahoo를 타야 한다.
    await _collect(
        _instrument("KOSPI", Market.KRX, InstrumentKind.INDEX, "^KS11"),
        date(2026, 7, 24),
        date(2026, 7, 31),
        korea,
        overseas,
        client=None,
    )

    assert korea.calls == []
    assert overseas.calls == [("KOSPI", "^KS11")]


@pytest.mark.asyncio
async def test_collect_warns_when_instrument_returns_no_bars(caplog: pytest.LogCaptureFixture) -> None:
    korea, overseas = _FakeKoreaService(bars=()), _FakeOverseasService()

    with caplog.at_level(logging.WARNING):
        result = await _collect(
            _instrument("005930", Market.KRX, InstrumentKind.EQUITY),
            date(2026, 7, 24),
            date(2026, 7, 31),
            korea,
            overseas,
            client=None,
        )

    assert result.bars == ()
    assert "ohlcv_instrument_returned_no_bars" in caplog.text


class _FakeInstrumentRepository:
    async def list_watched(self) -> list[Instrument]:
        return [_instrument("005930", Market.KRX, InstrumentKind.EQUITY)]


class _FakeOhlcvRepository:
    async def save_daily(self, results: object, snapshot_ts: datetime) -> int:
        del results, snapshot_ts
        return 0


class _FakeDatabase:
    async def dispose(self) -> None:
        pass


def _run_empty_ohlcv(options: OhlcvCollectOptions, *, scheduled: bool) -> RecordingIssueCollector:
    collector = RecordingIssueCollector()
    with (
        container.korea_daily_chart_service.override(providers.Object(_FakeKoreaService())),
        container.overseas_daily_chart_service.override(providers.Object(_FakeOverseasService())),
        container.instrument_repository.override(providers.Object(_FakeInstrumentRepository())),
        container.ohlcv_repository.override(providers.Object(_FakeOhlcvRepository())),
        container.database.override(providers.Object(_FakeDatabase())),
        container.issue_collector.override(providers.Object(collector)),
    ):
        import asyncio

        asyncio.run(main(options, scheduled=scheduled))
    return collector


def test_scheduled_ohlcv_zero_total_emits_empty_result() -> None:
    collector = _run_empty_ohlcv(build_options(["korea"]), scheduled=True)

    assert [event.kind for event in collector.events] == [IssueKind.EMPTY_RESULT]
    assert collector.events[0].context == {"scope": "korea", "fetched": 0}


def test_explicit_ohlcv_period_zero_total_does_not_emit() -> None:
    collector = _run_empty_ohlcv(
        build_options(["korea", "2026-07-01", "2026-07-02"]),
        scheduled=True,
    )

    assert collector.events == []

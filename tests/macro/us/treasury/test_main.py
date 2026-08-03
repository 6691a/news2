from datetime import date

import pytest
from dependency_injector import providers

from app.core._time import ET
from app.core.collection import BACKFILL_KEYWORD, BACKFILL_START
from app.core.containers import container
from app.core.models import utc_now
from app.macro.us.treasury.__main__ import build_options, main
from app.macro.us.treasury.schemas import TreasuryIntradayResult, TreasuryPhase, TreasuryProbeOptions, TreasurySeries
from app.notifications.models import IssueKind
from tests.notifications.fakes import RecordingIssueCollector


def test_build_options_defaults_to_ten_year_intraday() -> None:
    options = build_options([])

    assert options.phase is TreasuryPhase.INTRADAY
    assert options.series is TreasurySeries.US_10Y


def test_build_options_reads_series_for_intraday() -> None:
    options = build_options(["ZN"])

    assert options.phase is TreasuryPhase.INTRADAY
    assert options.series is TreasurySeries.ZN_FUTURE


def test_build_options_reads_single_final_date() -> None:
    options = build_options(["2026-07-30"])

    assert options.phase is TreasuryPhase.FINAL
    assert options.target_date == date(2026, 7, 30)
    assert options.start_date is None


def test_build_options_backfill_runs_from_baseline_to_today() -> None:
    options = build_options([BACKFILL_KEYWORD])

    assert options.phase is TreasuryPhase.BACKFILL
    assert options.start_date == BACKFILL_START
    assert options.target_date == utc_now().astimezone(ET).date()
    # 확정치 소스가 있는 계열은 10년물뿐이다.
    assert options.series is TreasurySeries.US_10Y


def test_build_options_rejects_unknown_argument() -> None:
    with pytest.raises(ValueError):
        build_options(["yesterday"])


class EmptyTreasuryService:
    async def collect_intraday(self, series: TreasurySeries) -> TreasuryIntradayResult:
        return TreasuryIntradayResult(series=series, bars=())

    async def collect_backfill(self, *args: object) -> tuple[object, ...]:
        del args
        return ()


class FakeTreasuryRepository:
    async def save_intraday(self, result: object, snapshot_ts: object) -> int:
        del result, snapshot_ts
        return 0

    async def save_final(self, result: object, snapshot_ts: object) -> int:
        del result, snapshot_ts
        return 0


class FakeDatabase:
    async def dispose(self) -> None:
        pass


def _run_empty_treasury(options: TreasuryProbeOptions) -> RecordingIssueCollector:
    collector = RecordingIssueCollector()
    with (
        container.us_treasury_yield_service.override(providers.Object(EmptyTreasuryService())),
        container.us_treasury_yield_repository.override(providers.Object(FakeTreasuryRepository())),
        container.database.override(providers.Object(FakeDatabase())),
        container.issue_collector.override(providers.Object(collector)),
    ):
        import asyncio

        asyncio.run(main(options, scheduled=True))
    return collector


def test_scheduled_treasury_intraday_zero_total_emits_empty_result() -> None:
    collector = _run_empty_treasury(TreasuryProbeOptions(phase=TreasuryPhase.INTRADAY))

    assert [event.kind for event in collector.events] == [IssueKind.EMPTY_RESULT]
    assert collector.events[0].context == {"phase": "intraday", "series": "US10Y", "fetched": 0}


def test_treasury_backfill_zero_total_does_not_emit() -> None:
    collector = _run_empty_treasury(
        TreasuryProbeOptions(
            phase=TreasuryPhase.BACKFILL,
            start_date=date(2026, 8, 3),
            target_date=date(2026, 8, 3),
        )
    )

    assert collector.events == []

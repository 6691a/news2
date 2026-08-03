from datetime import date

import pytest

from app.core._time import ET
from app.core.collection import BACKFILL_KEYWORD, BACKFILL_START
from app.core.models import utc_now
from app.macro.us.treasury.__main__ import build_options
from app.macro.us.treasury.schemas import TreasuryPhase, TreasurySeries


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

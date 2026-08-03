from datetime import date

import pytest

from app.core._time import KST
from app.core.collection import BACKFILL_KEYWORD, BACKFILL_START
from app.core.models import utc_now
from app.kis.korea.investor.__main__ import build_options
from app.kis.korea.investor.schemas import InvestorFlowPhase


def test_build_options_defaults_to_intraday() -> None:
    options = build_options([])

    assert options.phase is InvestorFlowPhase.INTRADAY
    assert options.trade_date is None
    assert options.start_date is None


def test_build_options_reads_single_trade_date() -> None:
    options = build_options(["2026-07-30"])

    assert options.phase is InvestorFlowPhase.FINAL
    assert options.trade_date == date(2026, 7, 30)
    assert options.start_date is None
    assert options.trade_dates() == (date(2026, 7, 30),)


def test_build_options_backfill_runs_from_baseline_to_today() -> None:
    options = build_options([BACKFILL_KEYWORD])

    assert options.phase is InvestorFlowPhase.FINAL
    assert options.start_date == BACKFILL_START
    assert options.trade_date == utc_now().astimezone(KST).date()
    # 2025-01-01은 수요일이라 주말 필터에 걸리지 않는다(공휴일은 0행으로 끝난다).
    assert options.trade_dates()[0] == BACKFILL_START


def test_build_options_rejects_unknown_argument() -> None:
    with pytest.raises(ValueError):
        build_options(["yesterday"])

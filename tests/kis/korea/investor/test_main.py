import asyncio
from datetime import date, datetime

import pytest
from dependency_injector import providers
from structlog.testing import capture_logs

from app.core._time import KST
from app.core.collection import BACKFILL_KEYWORD, BACKFILL_START
from app.core.containers import container
from app.core.models import utc_now
from app.kis.korea.investor import __main__ as main_module
from app.kis.korea.investor.__main__ import build_options, main
from app.kis.korea.investor.schemas import InvestorFlowPhase, InvestorFlowProbeOptions


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


def test_build_options_reads_explicit_period() -> None:
    options = build_options(["2026-06-01", "2026-07-31"])

    assert options.phase is InvestorFlowPhase.FINAL
    assert options.start_date == date(2026, 6, 1)
    assert options.trade_date == date(2026, 7, 31)
    # 6~7월 평일 45일. 주말만 미리 거르고 공휴일은 달력이 없어 그대로 호출한다(0행으로 끝난다).
    assert len(options.trade_dates()) == 45
    assert options.trade_dates()[0] == date(2026, 6, 1)


def test_build_options_rejects_reversed_period() -> None:
    with pytest.raises(ValueError, match="must not be after"):
        build_options(["2026-07-31", "2026-06-01"])


def test_build_options_rejects_extra_arguments() -> None:
    with pytest.raises(ValueError, match="period takes start and end"):
        build_options(["2026-06-01", "2026-07-31", "2026-08-01"])


def test_build_options_rejects_unknown_argument() -> None:
    with pytest.raises(ValueError):
        build_options(["yesterday"])


class FakeDatabase:
    """DB 풀 종료 호출을 기록한다."""

    async def dispose(self) -> None:
        """DB 풀 종료 호출을 받는다."""


class FakeRedis:
    """토큰 캐시 연결 종료 호출을 받는다."""

    async def aclose(self) -> None:
        """연결 종료 호출을 받는다."""


class FakeService:
    """수집 호출마다 응답 한 건을 돌려준다."""

    def __init__(self) -> None:
        self.units: list[InvestorFlowProbeOptions] = []

    async def collect_results(self, options: InvestorFlowProbeOptions, client: object) -> tuple[object, ...]:
        """호출한 옵션을 기록하고 응답 한 건을 돌려준다."""

        del client
        self.units.append(options)
        return (object(),)


class FakeRepository:
    """지정한 거래일에만 행을 저장한 것처럼 동작한다."""

    def __init__(self, saving_dates: set[date] | None = None) -> None:
        self._saving_dates = saving_dates

    async def save(self, results: object, options: InvestorFlowProbeOptions, snapshot_ts: datetime) -> int:
        """대상 거래일이면 2행, 아니면 0행을 저장했다고 답한다."""

        del results, snapshot_ts
        if self._saving_dates is None:
            return 2
        return 2 if options.trade_date in self._saving_dates else 0


def _run(options: InvestorFlowProbeOptions, repository: FakeRepository) -> list[dict[str, object]]:
    """컨테이너를 갈아끼워 main을 돌리고 남은 로그를 돌려준다."""

    with (
        container.korea_investor_flow_service.override(providers.Object(FakeService())),
        container.korea_investor_flow_repository.override(providers.Object(repository)),
        container.database.override(providers.Object(FakeDatabase())),
        container.redis_client.override(providers.Object(FakeRedis())),
        capture_logs() as logs,
    ):
        asyncio.run(main(options))
    return logs


def test_backfill_logs_the_range_that_actually_landed(monkeypatch: pytest.MonkeyPatch) -> None:
    # 호출 간 대기는 이 테스트의 관심사가 아니다.
    monkeypatch.setattr(main_module, "KIS_REQUEST_INTERVAL_SECONDS", 0)
    # 2025-01-01(수)~01-07(화) 중 영업일 5일을 요청하고, 그중 두 날짜만 저장된다.
    options = InvestorFlowProbeOptions(
        phase=InvestorFlowPhase.FINAL,
        start_date=date(2025, 1, 1),
        trade_date=date(2025, 1, 7),
    )

    logs = _run(options, FakeRepository({date(2025, 1, 3), date(2025, 1, 6)}))

    saved = [entry for entry in logs if entry["event"] == "investor_flow_saved"]
    assert len(saved) == 1
    assert saved[0]["trade_dates"] == 5
    assert saved[0]["saved"] == 4
    # 요청 구간(01-01~01-07)이 아니라 실제로 담긴 구간이어야 한다.
    assert (saved[0]["first_date"], saved[0]["last_date"]) == ("2025-01-03", "2025-01-06")


def test_backfill_without_saved_rows_leaves_the_range_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main_module, "KIS_REQUEST_INTERVAL_SECONDS", 0)
    options = InvestorFlowProbeOptions(
        phase=InvestorFlowPhase.FINAL,
        start_date=date(2025, 1, 1),
        trade_date=date(2025, 1, 3),
    )

    logs = _run(options, FakeRepository(set()))

    saved = [entry for entry in logs if entry["event"] == "investor_flow_saved"]
    assert (saved[0]["saved"], saved[0]["first_date"], saved[0]["last_date"]) == (0, "", "")


def test_intraday_falls_back_to_the_snapshot_trade_date() -> None:
    # 장중 옵션에는 거래일이 없다. repository와 같은 방식(스냅샷의 KST 날짜)으로 채운다.
    logs = _run(InvestorFlowProbeOptions(phase=InvestorFlowPhase.INTRADAY), FakeRepository())

    saved = [entry for entry in logs if entry["event"] == "investor_flow_saved"]
    today_in_korea = utc_now().astimezone(KST).date().isoformat()
    assert (saved[0]["first_date"], saved[0]["last_date"]) == (today_in_korea, today_in_korea)

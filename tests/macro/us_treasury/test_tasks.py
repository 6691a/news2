from datetime import UTC, date, datetime

import httpx
import pytest
from celery.exceptions import Retry
from yfinance.exceptions import YFRateLimitError

from app.core.celery import app
from app.macro.us_treasury import tasks
from app.macro.us_treasury.exceptions import TreasuryDataUnavailableError, YahooRetryableError
from app.macro.us_treasury.schemas import TreasuryPhase, TreasuryProbeOptions, TreasurySeries


def _capture_options(captured: list[TreasuryProbeOptions]):
    """main에 전달된 옵션을 기록한다."""

    async def fake_main(options: TreasuryProbeOptions) -> None:
        captured.append(options)

    return fake_main


def _capture_retry(captured: dict[str, object]):
    """celery가 넘긴 retry 인자를 기록하고 재시도 신호를 반환한다."""

    def fake_retry(**kwargs: object) -> Retry:
        captured.update(kwargs)
        return Retry()

    return fake_retry


def test_dispatch_final_fixes_target_date_at_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    """재시도가 자정을 넘어도 대상 날짜가 흔들리면 안 된다."""

    sent: list[tuple[object, ...]] = []
    # KST 10:00 = UTC 01:00 = ET 21:00(전일). 발사 시점의 ET 날짜는 7/27이다.
    monkeypatch.setattr(tasks, "utc_now", lambda: datetime(2026, 7, 28, 1, 0, tzinfo=UTC))
    monkeypatch.setattr(tasks.task_collect_final, "delay", lambda *args: sent.append(args))

    tasks.task_dispatch_final()

    assert sent == [("2026-07-27",)]


def test_collect_final_uses_dispatched_date_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """collect_final은 오늘 날짜를 재계산하지 않고 받은 날짜만 쓴다."""

    captured: list[TreasuryProbeOptions] = []
    monkeypatch.setattr(tasks, "main", _capture_options(captured))
    monkeypatch.setattr(tasks, "utc_now", lambda: datetime(2026, 7, 29, 3, 0, tzinfo=UTC))

    tasks.task_collect_final("2026-07-27")

    assert len(captured) == 1
    assert captured[0].phase is TreasuryPhase.FINAL
    assert captured[0].series is TreasurySeries.US_10Y
    assert captured[0].target_date == date(2026, 7, 27)


def test_collect_intraday_passes_the_requested_series(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[TreasuryProbeOptions] = []
    monkeypatch.setattr(tasks, "main", _capture_options(captured))

    tasks.task_collect_intraday("ZN")
    tasks.task_collect_intraday("US10Y")

    assert [options.series for options in captured] == [
        TreasurySeries.ZN_FUTURE,
        TreasurySeries.US_10Y,
    ]
    assert all(options.phase is TreasuryPhase.INTRADAY for options in captured)
    assert all(options.target_date is None for options in captured)


def test_collect_final_retries_on_a_flat_thirty_minute_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    # H.15 공표 지연은 지수 백오프로 물러나면 첫 재시도가 너무 빨리 소진된다.
    captured: dict[str, object] = {}

    def raise_unavailable(_options: object) -> None:
        raise TreasuryDataUnavailableError("아직 공표되지 않았다")

    monkeypatch.setattr(tasks, "main", raise_unavailable)
    monkeypatch.setattr(tasks.task_collect_final, "retry", _capture_retry(captured))

    with pytest.raises(Retry):
        tasks.task_collect_final("2026-07-27")

    assert "countdown" not in captured
    assert tasks.task_collect_final.default_retry_delay == 30 * 60
    assert tasks.task_collect_final.max_retries == 4


def test_intraday_task_retries_on_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def boom(_options: object) -> None:
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(tasks, "main", boom)
    monkeypatch.setattr(tasks.task_collect_intraday, "retry", _capture_retry(captured))

    with pytest.raises(Retry):
        tasks.task_collect_intraday("US10Y")

    # 15분 뒤 다음 회차가 오므로 짧게 물러난다.
    assert "countdown" in captured
    assert tasks.task_collect_intraday.max_retries == 2


def test_intraday_task_retries_on_yfinance_error(monkeypatch: pytest.MonkeyPatch) -> None:
    # 연결·타임아웃은 다음 회차를 기다릴 이유가 없다. 짧게 물러났다가 다시 부른다.
    captured: dict[str, object] = {}

    def boom(_options: object) -> None:
        raise YahooRetryableError("boom")

    monkeypatch.setattr(tasks, "main", boom)
    monkeypatch.setattr(tasks.task_collect_intraday, "retry", _capture_retry(captured))

    with pytest.raises(Retry):
        tasks.task_collect_intraday("US10Y")

    assert "countdown" in captured


def test_intraday_task_does_not_retry_on_yfinance_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    # 엣지 차단은 분 단위로 풀리지 않는다. 재시도는 익명 쿼터만 더 소모한다.
    captured: dict[str, object] = {}

    def rate_limited(_options: object) -> None:
        raise YFRateLimitError

    monkeypatch.setattr(tasks, "main", rate_limited)
    monkeypatch.setattr(tasks.task_collect_intraday, "retry", _capture_retry(captured))

    with pytest.raises(YFRateLimitError):
        tasks.task_collect_intraday("US10Y")

    assert captured == {}


def test_beat_schedule_polls_both_series_and_dispatches_final() -> None:
    schedule = app.conf.beat_schedule

    assert "app.macro.us_treasury.tasks" in app.conf.imports
    assert schedule["us-treasury-intraday-evening"]["task"] == "macro.us_treasury.collect_intraday"
    assert schedule["us-treasury-intraday-evening"]["args"] == ("US10Y",)
    assert schedule["us-treasury-intraday-morning"]["args"] == ("US10Y",)
    assert schedule["us-treasury-futures-intraday"]["args"] == ("ZN",)
    assert schedule["us-treasury-final"]["task"] == "macro.us_treasury.dispatch_final"
    assert tasks.task_collect_intraday.name == "macro.us_treasury.collect_intraday"
    assert tasks.task_collect_final.name == "macro.us_treasury.collect_final"
    assert tasks.task_dispatch_final.name == "macro.us_treasury.dispatch_final"

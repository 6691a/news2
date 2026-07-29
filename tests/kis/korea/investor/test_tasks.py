import httpx
import pytest
from celery.exceptions import Retry

from app.kis.korea.investor import tasks


def _boom(_options: object) -> None:
    """수집 중 네트워크 오류가 난 상황을 만든다."""

    raise httpx.ConnectError("boom")


def _capture_retry(captured: dict[str, object]):
    """celery 가 넘긴 retry 인자를 기록하고 재시도 신호를 반환한다."""

    def fake_retry(**kwargs: object) -> Retry:
        captured.update(kwargs)
        return Retry()

    return fake_retry


def test_fixed_time_tasks_retry_on_a_flat_five_minute_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    # 갱신 시각이 정해진 수집은 지수 백오프(2초, 4초)로 물러나면 의미가 없다.
    # celery 는 retry_backoff 가 falsy 일 때만 countdown 주입을 건너뛰고
    # default_retry_delay 로 떨어진다.
    captured: dict[str, object] = {}
    monkeypatch.setattr(tasks, "main", _boom)
    monkeypatch.setattr(tasks.task_collect_stock_intraday, "retry", _capture_retry(captured))

    with pytest.raises(Retry):
        tasks.task_collect_stock_intraday()

    assert "countdown" not in captured
    assert tasks.task_collect_stock_intraday.default_retry_delay == 5 * 60
    assert tasks.task_collect_stock_intraday.max_retries == 3
    assert tasks.task_collect_final.default_retry_delay == 5 * 60
    assert tasks.task_collect_final.max_retries == 3


def test_market_task_keeps_exponential_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    # 시장 집계는 30분마다 다음 회차가 오므로 짧게 물러나는 편이 맞다.
    captured: dict[str, object] = {}
    monkeypatch.setattr(tasks, "main", _boom)
    monkeypatch.setattr(tasks.task_collect_market_intraday, "retry", _capture_retry(captured))

    with pytest.raises(Retry):
        tasks.task_collect_market_intraday()

    assert "countdown" in captured


def test_response_errors_are_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    # rt_cd 가 0이 아닌 응답은 다시 물어봐도 같은 답이 온다. httpx 오류만 재시도한다.
    def raise_value_error(_options: object) -> None:
        raise ValueError("모의투자 설정")

    monkeypatch.setattr(tasks, "main", raise_value_error)

    with pytest.raises(ValueError):
        tasks.task_collect_stock_intraday()

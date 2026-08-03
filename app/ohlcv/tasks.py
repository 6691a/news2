"""확정 일봉 수집 Celery task."""

import asyncio

import httpx

from app.core.celery import app

# __main__을 그대로 재사용한다. 수동 실행(python -m app.ohlcv)과 배치가 같은 코드를
# 타므로 중복이 없다. import 시점에 컨테이너 wiring과 로깅 설정도 함께 끝난다.
from app.ohlcv.__main__ import main
from app.ohlcv.exceptions import YahooRetryableError
from app.ohlcv.schemas import OhlcvCollectOptions, OhlcvScope


# 재시도 대상은 네트워크·타임아웃과 yfinance의 일시적인 실패뿐이다.
# OhlcvSourceError(rt_cd != "0")는 다시 물어봐도 같은 답이라 여기에 넣지 않는다.
# YFRateLimitError도 감싸지 않아 재시도되지 않는다.
RETRY_FOR = (httpx.HTTPError, YahooRetryableError)

# 하루 1회뿐이라 놓치면 그 날 확정값이 비어 있는다. 5분 간격으로 3회까지 다시 시도한다.
# 최근 구간을 겹쳐 조회하므로 다음 날 회차가 빠진 날을 메우기는 하지만, 그날의
# 데일리 리포트는 이미 늦는다.
# retry_backoff는 기본값이 False라 지정하지 않는다. falsy면 celery가 countdown을
# 주입하지 않고 default_retry_delay로 떨어진다(celery/app/task.py:756).
DAILY_RETRY_POLICY = {
    "autoretry_for": RETRY_FOR,
    "default_retry_delay": 5 * 60,
    "max_retries": 3,
}


@app.task(name="ohlcv.collect_korea_daily", **DAILY_RETRY_POLICY)
def task_collect_korea_daily() -> None:
    """국내 추적 종목의 확정 일봉을 최근 구간만큼 수집해 저장한다.

    지난 기간 백필은 `python -m app.ohlcv korea 2024-01-01 2026-07-31`로 한다.
    """

    asyncio.run(main(OhlcvCollectOptions(scope=OhlcvScope.KOREA)))


@app.task(name="ohlcv.collect_overseas_daily", **DAILY_RETRY_POLICY)
def task_collect_overseas_daily() -> None:
    """해외 추적 종목의 확정 일봉을 최근 구간만큼 수집해 저장한다.

    지난 기간 백필은 `python -m app.ohlcv overseas 2024-01-01 2026-07-31`로 한다.
    """

    asyncio.run(main(OhlcvCollectOptions(scope=OhlcvScope.OVERSEAS)))

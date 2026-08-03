"""미국 국채 수익률·국채선물 수집 Celery task."""

import asyncio
from datetime import date

import httpx

from app.core._time import ET
from app.core.celery import app
from app.core.models import utc_now

# __main__을 그대로 재사용한다. 수동 실행(python -m app.macro.us.treasury)과
# 배치가 같은 코드를 타므로 중복이 없다. import 시점에 컨테이너 wiring과
# 로깅 설정도 함께 끝난다.
from app.macro.us.treasury.__main__ import main
from app.macro.us.treasury.exceptions import TreasuryDataUnavailableError, YahooRetryableError
from app.macro.us.treasury.schemas import TreasuryPhase, TreasuryProbeOptions, TreasurySeries


# 재시도 대상은 네트워크·타임아웃과 yfinance의 일시적인 실패뿐이다.
# YFRateLimitError는 YahooRetryableError로 감싸지 않아 여기에 걸리지 않는다.
RETRY_FOR = (httpx.HTTPError, YahooRetryableError)

# 15분 뒤 다음 회차가 오므로 짧게 물러난다. 멱등 저장이라 겹쳐도 무해하다.
# retry_jitter는 기본값이 True다(celery/app/autoretry.py:30).
INTRADAY_RETRY_POLICY = {
    "autoretry_for": RETRY_FOR,
    # celery는 factor=int(max(1.0, retry_backoff))로 2^n * factor 초를 쓴다.
    "retry_backoff": 60,
    "max_retries": 2,
}

# H.15 공표 지연을 흡수하도록 30분 간격 4회(+2시간)까지 기다린다.
# 미국 휴장일에는 값이 영영 오지 않아 재시도 소진 후 오류 로그로 끝난다(예상된 소음).
# retry_backoff는 기본값이 False라 지정하지 않는다. falsy면 celery가 countdown을
# 주입하지 않고 default_retry_delay로 떨어진다(celery/app/task.py:756).
FINAL_RETRY_POLICY = {
    "autoretry_for": (*RETRY_FOR, TreasuryDataUnavailableError),
    "default_retry_delay": 30 * 60,
    "max_retries": 4,
}


@app.task(name="macro.us.treasury.collect_intraday", **INTRADAY_RETRY_POLICY)
def task_collect_intraday(series: str) -> None:
    """계열 하나의 장중 1분봉을 한 번 수집해 저장한다.

    수익률(^TNX)과 국채선물(ZN=F)이 같은 task를 공용한다. beat가 계열 값을 인자로
    넘긴다. 폐장·휴장 시간대 폴링은 (series, event_ts) 중복으로 전부 skip된다.

    Args:
        series: 수집할 계열 값("US10Y" 또는 "ZN").
    """

    asyncio.run(
        main(
            TreasuryProbeOptions(
                phase=TreasuryPhase.INTRADAY,
                series=TreasurySeries(series),
            ),
            scheduled=True,
        )
    )


@app.task(name="macro.us.treasury.dispatch_final")
def task_dispatch_final() -> None:
    """발사 시점의 ET 날짜를 고정해 task_collect_final에 넘긴다.

    재시도가 자정을 넘어도 대상 날짜가 흔들리면 안 된다. celery autoretry는 원래
    인자를 보존하므로 날짜를 인자로 박아 넘긴다. 이 task 자체는 I/O가 없어
    재시도가 필요 없다.
    """

    task_collect_final.delay(utc_now().astimezone(ET).date().isoformat())


@app.task(name="macro.us.treasury.collect_final", **FINAL_RETRY_POLICY)
def task_collect_final(target_date: str) -> None:
    """지정한 미국 영업일의 확정 수익률(FRED DGS10)을 수집해 저장한다.

    Args:
        target_date: dispatch 시점에 고정된 ET 영업일(`YYYY-MM-DD`).
    """

    asyncio.run(
        main(
            TreasuryProbeOptions(
                phase=TreasuryPhase.FINAL,
                target_date=date.fromisoformat(target_date),
            ),
            scheduled=True,
        )
    )

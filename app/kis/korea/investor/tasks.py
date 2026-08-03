"""국내 투자자 수급 수집 Celery task."""

import asyncio

import httpx

from app.core.celery import app
from app.core.models import utc_now
from app.core._time import KST

# __main__을 그대로 재사용한다. 수동 실행(python -m app.kis.korea.investor)과
# 배치가 같은 코드를 타므로 중복이 없다. import 시점에 컨테이너 wiring과
# 로깅 설정도 함께 끝난다.
from app.kis.korea.investor.__main__ import main
from app.kis.korea.investor.schemas import (
    InvestorFlowPhase,
    InvestorFlowProbeOptions,
    InvestorFlowScope,
)


# 재시도 대상은 네트워크·타임아웃뿐이다. rt_cd가 0이 아닌 응답 오류는 다시
# 물어봐도 같은 답이 온다.
RETRY_FOR = (httpx.HTTPError,)

# 갱신 시각이 정해진 수집(종목 가집계, 마감 확정치)은 한 번 놓치면 다음 갱신까지
# 구멍이 난다. 5분 간격으로 3회까지 다시 시도한다(최대 +15분).
# retry_backoff는 기본값이 False라 지정하지 않는다. falsy면 celery가 countdown을
# 주입하지 않고 default_retry_delay로 떨어진다(celery/app/task.py:756).
FIXED_TIME_RETRY_POLICY = {
    "autoretry_for": RETRY_FOR,
    "default_retry_delay": 5 * 60,
    "max_retries": 3,
}

# 시장 집계는 30분마다 다시 오므로 짧게 물러났다가 포기한다. 다음 회차가 곧 온다.
# retry_jitter는 기본값이 True다(celery/app/autoretry.py:30).
PERIODIC_RETRY_POLICY = {
    "autoretry_for": RETRY_FOR,
    # 1분 발급 제한을 넘기려면 첫 재시도가 60초 뒤여야 한다.
    # celery는 factor=int(max(1.0, retry_backoff))로 2^n * factor 초를 쓴다.
    "retry_backoff": 60,
    "max_retries": 3,
}


@app.task(name="kis.korea.investor.collect_stock_intraday", **FIXED_TIME_RETRY_POLICY)
def task_collect_stock_intraday() -> None:
    """종목별 장중 가집계를 한 번 수집해 저장한다.

    KIS 입력시간에만 갱신되는 데이터라 beat가 그 시각에만 호출한다. 실패하면
    5분 간격으로 3회까지 다시 시도한다.

    재시도는 아무것도 저장되지 않았을 때만 일어나므로(수집 실패 시 트랜잭션이
    열리지도 않는다) 중복 걱정이 없다. 11:21·13:21 수집의 2회차 이후 재시도는
    30분 슬롯 경계를 넘어 snapshot_ts가 한 칸 뒤로 붙지만, 겹칠 행이 없어
    데이터는 그대로다.
    """

    asyncio.run(
        main(
            InvestorFlowProbeOptions(
                phase=InvestorFlowPhase.INTRADAY,
                scope=InvestorFlowScope.STOCK,
            ),
            scheduled=True,
        )
    )


@app.task(name="kis.korea.investor.collect_market_intraday", **PERIODIC_RETRY_POLICY)
def task_collect_market_intraday() -> None:
    """시장 단위 장중 집계를 한 번 수집해 저장한다."""

    asyncio.run(
        main(
            InvestorFlowProbeOptions(
                phase=InvestorFlowPhase.INTRADAY,
                scope=InvestorFlowScope.MARKET,
            ),
            scheduled=True,
        )
    )


@app.task(name="kis.korea.investor.collect_final", **FIXED_TIME_RETRY_POLICY)
def task_collect_final() -> None:
    """오늘(한국 날짜) 장 마감 확정 투자자 수급을 종목·시장 함께 수집해 저장한다.

    하루 1회뿐이라 실패하면 5분 간격으로 3회까지 다시 시도한다.
    지난 날짜 백필은 `python -m app.kis.korea.investor 2026-07-24`로 한다.
    """

    asyncio.run(
        main(
            InvestorFlowProbeOptions(
                phase=InvestorFlowPhase.FINAL,
                trade_date=utc_now().astimezone(KST).date(),
            ),
            scheduled=True,
        )
    )

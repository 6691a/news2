"""국내 투자자 수급 수집·저장 엔트리포인트.

python -m app.kis.korea.investor               # 장중 가집계
python -m app.kis.korea.investor 2026-07-30    # 그 날짜의 마감 확정치
python -m app.kis.korea.investor backfill      # 기준 시작일(2025-01-01)부터 오늘까지 확정치
"""

import asyncio
import sys
from collections.abc import Sequence
from datetime import date
from typing import Annotated

import httpx
from dependency_injector.wiring import Provide, inject
from redis.asyncio import Redis

from app.core._time import KST
from app.core.collection import BACKFILL_KEYWORD, BACKFILL_START, KIS_REQUEST_INTERVAL_SECONDS
from app.core.containers import Container, container
from app.core.database import Database
from app.core.logging import configure_logging, get_logger
from app.core.models import utc_now
from app.kis.korea.investor.repository import KISInvestorFlowRepository, snapshot_slot_start
from app.kis.korea.investor.schemas import InvestorFlowPhase, InvestorFlowProbeOptions
from app.kis.korea.investor.service import KISKoreaInvestorFlowService
from app.notifications.collector import IssueEventRecorder, safe_record_issue
from app.notifications.models import IssueEvent, IssueKind


configure_logging(container.settings())
logger = get_logger(__name__)


def build_options(argv: Sequence[str]) -> InvestorFlowProbeOptions:
    """명령행 인자로 실행 옵션을 만든다.

    Args:
        argv: 프로그램 이름을 제외한 명령행 인자.

    Returns:
        인자가 없으면 장중 가집계 옵션, `YYYY-MM-DD`를 주면 그 날짜의 마감 확정치 옵션,
        `backfill`이면 기준 시작일부터 오늘까지의 마감 확정치 옵션.

    Raises:
        ValueError: 날짜 인자가 `backfill`도 ISO 8601 형식도 아닌 경우.
    """

    if not argv:
        return InvestorFlowProbeOptions(phase=InvestorFlowPhase.INTRADAY)

    if argv[0] == BACKFILL_KEYWORD:
        return InvestorFlowProbeOptions(
            phase=InvestorFlowPhase.FINAL,
            start_date=BACKFILL_START,
            trade_date=utc_now().astimezone(KST).date(),
        )

    return InvestorFlowProbeOptions(
        phase=InvestorFlowPhase.FINAL,
        trade_date=date.fromisoformat(argv[0]),
    )


@inject
async def main(
    options: InvestorFlowProbeOptions,
    service: Annotated[
        KISKoreaInvestorFlowService,
        Provide[Container.korea_investor_flow_service],
    ],
    repository: Annotated[
        KISInvestorFlowRepository,
        Provide[Container.korea_investor_flow_repository],
    ],
    database: Annotated[
        Database,
        Provide[Container.database],
    ],
    redis: Annotated[
        Redis,
        Provide[Container.redis_client],
    ],
    issue_collector: Annotated[
        IssueEventRecorder,
        Provide[Container.issue_collector],
    ],
    scheduled: bool = False,
) -> None:
    """투자자 수급을 한 번 수집해 DB에 저장한다.

    Args:
        options: 장중 또는 장 마감 수집 옵션.
        service: KIS 투자자 수급 수집 서비스.
        repository: 수집 결과를 저장할 repository.
        database: 종료 시 정리할 데이터베이스 자원.
        redis: 종료 시 정리할 토큰 캐시 연결.
        issue_collector: 운영 이슈 이벤트 기록기.
        scheduled: Celery 정기 실행 여부.
    """

    # 요청은 순차 전송되지만 한 스냅샷으로 묶어야 UNIQUE 키와 분석이 단순해진다.
    # 슬롯 시작으로 내려야 Celery 재시도가 중복 대신 무시로 끝난다.
    snapshot_ts = snapshot_slot_start(utc_now())
    try:
        # 장중·단일 마감은 원소 하나짜리 목록이라 아래 루프가 기존 동작 그대로다.
        # 백필만 거래일 수만큼 돈다 — 종목 확정 TR이 날짜를 하나씩만 받기 때문이다.
        units = [options.model_copy(update={"start_date": None, "trade_date": day}) for day in options.trade_dates()]
        if not units:
            units = [options]

        responses = 0
        saved = 0
        saved_dates: list[date] = []
        async with httpx.AsyncClient() as client:
            for index, unit in enumerate(units):
                # 거래일이 바뀔 때도 KIS 초당 거래건수 제한을 지켜야 한다. 서비스가 TR
                # 사이에 쓰는 것과 같은 간격을 쓴다 — 제한은 호출자가 누구든 동일하다.
                if index:
                    await asyncio.sleep(KIS_REQUEST_INTERVAL_SECONDS)
                results = await service.collect_results(unit, client)
                responses += len(results)
                unit_saved = await repository.save(results, unit, snapshot_ts)
                saved += unit_saved
                if unit_saved:
                    # repository와 같은 방식으로 거래일을 정한다. 장중 옵션에는 날짜가 없다.
                    saved_dates.append(unit.trade_date or snapshot_ts.astimezone(KST).date())

        # units가 오름차순이라 saved_dates도 정렬 상태다(trade_dates()가 보장한다).
        logger.info(
            "investor_flow_saved",
            phase=options.phase.value,
            trade_dates=len(units),
            responses=responses,
            saved=saved,
            # 요청 구간이 아니라 실제로 행이 담긴 구간이다. 소스가 기준 시작일부터
            # 주지 못하거나 중간이 통째로 비어도 여기서만 드러난다.
            first_date=saved_dates[0].isoformat() if saved_dates else "",
            last_date=saved_dates[-1].isoformat() if saved_dates else "",
            snapshot_ts=snapshot_ts.isoformat(),
        )
        if scheduled and options.phase is InvestorFlowPhase.INTRADAY and responses == 0:
            await safe_record_issue(
                issue_collector,
                IssueEvent.create(
                    kind=IssueKind.EMPTY_RESULT,
                    service="kis.korea.investor",
                    operation="collect_intraday",
                    stable_dimension=options.scope.value,
                    summary="Scheduled investor-flow collection returned no responses.",
                    metric_name="fetched",
                    observed_value=0,
                    expected_value=1,
                    context={"phase": options.phase.value, "fetched": 0},
                ),
            )
    finally:
        await database.dispose()
        await redis.aclose()


container.wire(modules=[sys.modules[__name__]], warn_unresolved=True)


if __name__ == "__main__":
    asyncio.run(main(build_options(sys.argv[1:])))

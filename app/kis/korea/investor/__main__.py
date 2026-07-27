"""국내 투자자 수급 수집·저장 엔트리포인트."""

import asyncio
import sys
from collections.abc import Sequence
from datetime import date
from typing import Annotated

import httpx
from dependency_injector.wiring import Provide, inject
from redis.asyncio import Redis

from app.core.containers import Container, container
from app.core.database import Database
from app.core.logging import configure_logging, get_logger
from app.core.models import utc_now
from app.kis.korea.investor.repository import KISInvestorFlowRepository, snapshot_slot_start
from app.kis.korea.investor.schemas import InvestorFlowPhase, InvestorFlowProbeOptions
from app.kis.korea.investor.service import KISKoreaInvestorFlowService


configure_logging(container.settings())
logger = get_logger(__name__)


def build_options(argv: Sequence[str]) -> InvestorFlowProbeOptions:
    """명령행 인자로 실행 옵션을 만든다.

    Args:
        argv: 프로그램 이름을 제외한 명령행 인자.

    Returns:
        인자가 없으면 장중 가집계 옵션, `YYYY-MM-DD`를 주면 그 날짜의 마감 확정치 옵션.

    Raises:
        ValueError: 날짜 인자가 ISO 8601 형식이 아닌 경우.
    """

    if not argv:
        return InvestorFlowProbeOptions(phase=InvestorFlowPhase.INTRADAY)

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
) -> None:
    """투자자 수급을 한 번 수집해 DB에 저장한다.

    Args:
        options: 장중 또는 장 마감 수집 옵션.
        service: KIS 투자자 수급 수집 서비스.
        repository: 수집 결과를 저장할 repository.
        database: 종료 시 정리할 데이터베이스 자원.
        redis: 종료 시 정리할 토큰 캐시 연결.
    """

    # 요청은 순차 전송되지만 한 스냅샷으로 묶어야 UNIQUE 키와 분석이 단순해진다.
    # 슬롯 시작으로 내려야 Celery 재시도가 중복 대신 무시로 끝난다.
    snapshot_ts = snapshot_slot_start(utc_now())
    try:
        async with httpx.AsyncClient() as client:
            results = await service.collect_results(options, client)

        saved = await repository.save(results, options, snapshot_ts)
        logger.info(
            "investor_flow_saved",
            phase=options.phase.value,
            responses=len(results),
            saved=saved,
            snapshot_ts=snapshot_ts.isoformat(),
        )
    finally:
        await database.dispose()
        await redis.aclose()


container.wire(modules=[sys.modules[__name__]], warn_unresolved=True)


if __name__ == "__main__":
    asyncio.run(main(build_options(sys.argv[1:])))

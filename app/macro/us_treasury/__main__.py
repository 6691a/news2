"""미국 국채 수익률·국채선물 수집·저장 엔트리포인트."""

import asyncio
import sys
from collections.abc import Sequence
from datetime import date
from typing import Annotated

import httpx
from dependency_injector.wiring import Provide, inject

from app.core.containers import Container, container
from app.core.database import Database
from app.core.logging import configure_logging, get_logger
from app.core.models import utc_now
from app.macro.us_treasury.repository import UsTreasuryYieldRepository
from app.macro.us_treasury.schemas import TreasuryPhase, TreasuryProbeOptions, TreasurySeries
from app.macro.us_treasury.service import UsTreasuryYieldService


configure_logging(container.settings())
logger = get_logger(__name__)


def build_options(argv: Sequence[str]) -> TreasuryProbeOptions:
    """명령행 인자로 실행 옵션을 만든다.

    Args:
        argv: 프로그램 이름을 제외한 명령행 인자.

    Returns:
        인자가 없으면 10년물 수익률 장중 수집 옵션, 계열 값(`US10Y`·`ZN`)을 주면 그
        계열의 장중 수집 옵션, `YYYY-MM-DD`를 주면 그 날짜의 확정치 수집 옵션.

    Raises:
        ValueError: 인자가 계열 값도 ISO 8601 날짜도 아닌 경우.
    """

    if not argv:
        return TreasuryProbeOptions(phase=TreasuryPhase.INTRADAY)

    argument = argv[0]
    if argument in {member.value for member in TreasurySeries}:
        return TreasuryProbeOptions(
            phase=TreasuryPhase.INTRADAY,
            series=TreasurySeries(argument),
        )

    return TreasuryProbeOptions(
        phase=TreasuryPhase.FINAL,
        target_date=date.fromisoformat(argument),
    )


@inject
async def main(
    options: TreasuryProbeOptions,
    service: Annotated[
        UsTreasuryYieldService,
        Provide[Container.us_treasury_yield_service],
    ],
    repository: Annotated[
        UsTreasuryYieldRepository,
        Provide[Container.us_treasury_yield_repository],
    ],
    database: Annotated[
        Database,
        Provide[Container.database],
    ],
) -> None:
    """미국 국채 지표를 한 번 수집해 DB에 저장한다.

    Args:
        options: 장중 또는 확정치 수집 옵션.
        service: 미국 국채 수집 서비스.
        repository: 수집 결과를 저장할 repository.
        database: 종료 시 정리할 데이터베이스 자원.
    """

    # event_ts·observation_date가 dedupe 키라 snapshot_ts는 눈금을 맞출 필요가 없다.
    snapshot_ts = utc_now()
    try:
        if options.phase is TreasuryPhase.INTRADAY:
            result = await service.collect_intraday(options.series)
            saved = await repository.save_intraday(result, snapshot_ts)
            fetched = len(result.bars)
            target_date = ""
        else:
            assert options.target_date is not None
            async with httpx.AsyncClient() as client:
                observation = await service.collect_final(options.series, options.target_date, client)
            saved = await repository.save_final(observation, snapshot_ts)
            fetched = 1
            target_date = observation.observation_date.isoformat()

        logger.info(
            "us_treasury_saved",
            phase=options.phase.value,
            series=options.series.value,
            target_date=target_date,
            fetched=fetched,
            saved=saved,
            snapshot_ts=snapshot_ts.isoformat(),
        )
    finally:
        await database.dispose()


container.wire(modules=[sys.modules[__name__]], warn_unresolved=True)


if __name__ == "__main__":
    asyncio.run(main(build_options(sys.argv[1:])))

"""미국 국채 수익률·국채선물 수집·저장 엔트리포인트.

python -m app.macro.us.treasury                          # 10년물 장중 1분봉
python -m app.macro.us.treasury ZN                       # 국채선물 장중 1분봉
python -m app.macro.us.treasury 2026-07-30               # 그 날짜의 확정 수익률
python -m app.macro.us.treasury backfill                 # 기준 시작일(2025-01-01)부터 오늘까지
python -m app.macro.us.treasury 2026-06-01 2026-07-31    # 지정한 구간만 확정 수익률

장중 1분봉에는 backfill 경로가 없다. Yahoo가 1분봉을 30일까지만 보관해 과거를 채울 수
없고, 가동 시작 시점이 곧 그 그레인 데이터의 시작이다. 조사하고 없는 것이지 빠뜨린 게 아니다.
"""

import asyncio
import sys
from collections.abc import Sequence
from datetime import date
from typing import Annotated

import httpx
from dependency_injector.wiring import Provide, inject

from app.core._time import ET
from app.core.collection import BACKFILL_KEYWORD, BACKFILL_START
from app.core.containers import Container, container
from app.core.database import Database
from app.core.logging import configure_logging, get_logger
from app.core.sentry import SentryRuntime, configure_sentry, flush_sentry
from app.core.models import utc_now
from app.macro.us.treasury.repository import UsTreasuryYieldRepository
from app.macro.us.treasury.schemas import TreasuryPhase, TreasuryProbeOptions, TreasurySeries
from app.macro.us.treasury.service import UsTreasuryYieldService


app_settings = container.settings()
configure_sentry(app_settings, SentryRuntime.SCRIPT)
configure_logging(app_settings)
logger = get_logger(__name__)


def build_options(argv: Sequence[str]) -> TreasuryProbeOptions:
    """명령행 인자로 실행 옵션을 만든다.

    Args:
        argv: 프로그램 이름을 제외한 명령행 인자.
            `[series] | [backfill] | [date] | [start end]` 형식이며 전부 생략할 수 있다.

    Returns:
        인자가 없으면 10년물 수익률 장중 수집 옵션, 계열 값(`US10Y`·`ZN`)을 주면 그
        계열의 장중 수집 옵션, `YYYY-MM-DD` 하나면 그 날짜의 확정치 수집 옵션,
        날짜 둘이면 그 구간의 확정치 수집 옵션, `backfill`이면 기준 시작일부터
        오늘까지의 확정치 수집 옵션.

    Raises:
        ValueError: 인자가 계열 값도 `backfill`도 ISO 8601 날짜도 아니거나, 인자가 너무
            많은 경우.
    """

    if not argv:
        return TreasuryProbeOptions(phase=TreasuryPhase.INTRADAY)

    argument = argv[0]
    if argument in {member.value for member in TreasurySeries}:
        return TreasuryProbeOptions(
            phase=TreasuryPhase.INTRADAY,
            series=TreasurySeries(argument),
        )

    if argument == BACKFILL_KEYWORD:
        # 종료일은 ET 오늘. 오늘치가 아직 공표 전이면 결측으로 와서 그냥 빠진다.
        return TreasuryProbeOptions(
            phase=TreasuryPhase.BACKFILL,
            start_date=BACKFILL_START,
            target_date=utc_now().astimezone(ET).date(),
        )

    if len(argv) > 2:
        raise ValueError("period takes start and end (YYYY-MM-DD)")

    if len(argv) == 2:
        # 구간을 직접 주면 기준 시작일 대신 그 구간만 받는다. backfill과 같은 경로를
        # 타므로 결측(휴장·미공표)은 예외 없이 건너뛴다.
        return TreasuryProbeOptions(
            phase=TreasuryPhase.BACKFILL,
            start_date=date.fromisoformat(argument),
            target_date=date.fromisoformat(argv[1]),
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
        first_date = ""
        target_date = ""
        if options.phase is TreasuryPhase.INTRADAY:
            result = await service.collect_intraday(options.series)
            saved = await repository.save_intraday(result, snapshot_ts)
            fetched = len(result.bars)
        else:
            assert options.target_date is not None
            async with httpx.AsyncClient() as client:
                if options.phase is TreasuryPhase.BACKFILL:
                    assert options.start_date is not None
                    observations = await service.collect_backfill(
                        options.series,
                        options.start_date,
                        options.target_date,
                        client,
                    )
                else:
                    observations = (await service.collect_final(options.series, options.target_date, client),)

            saved = await repository.save_final(observations, snapshot_ts)
            fetched = len(observations)
            # 요청 시작일보다 늦게 시작하는 시리즈가 있으므로 실제 첫 관측일을 남긴다.
            first_date = observations[0].observation_date.isoformat() if observations else ""
            target_date = observations[-1].observation_date.isoformat() if observations else ""

        logger.info(
            "us_treasury_saved",
            phase=options.phase.value,
            series=options.series.value,
            first_date=first_date,
            target_date=target_date,
            fetched=fetched,
            saved=saved,
            snapshot_ts=snapshot_ts.isoformat(),
        )
    finally:
        await database.dispose()


container.wire(modules=[sys.modules[__name__]], warn_unresolved=True)


if __name__ == "__main__":
    try:
        asyncio.run(main(build_options(sys.argv[1:])))
    finally:
        flush_sentry()

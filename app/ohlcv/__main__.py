"""확정 일봉 수집·저장 엔트리포인트.

python -m app.ohlcv                                  # 국내·해외 최근 구간
python -m app.ohlcv korea                            # 국내만
python -m app.ohlcv korea backfill                   # 기준 시작일(2025-01-01)부터 오늘까지
python -m app.ohlcv overseas 2025-06-01              # 지정일부터 오늘까지
python -m app.ohlcv overseas 2025-01-01 2026-07-31   # 기간 지정
"""

import asyncio
import sys
from collections.abc import Sequence
from datetime import date, datetime
from typing import Annotated

import httpx
from dependency_injector.wiring import Provide, inject

from app.core.collection import BACKFILL_KEYWORD, BACKFILL_START
from app.core.containers import Container, container
from app.core.database import Database
from app.core.logging import configure_logging, get_logger
from app.core.sentry import SentryRuntime, configure_sentry, flush_sentry
from app.core.models import utc_now
from app.instruments.models import Instrument, InstrumentKind, Market
from app.instruments.repository import InstrumentRepository
from app.ohlcv.korea import KISKoreaDailyChartService
from app.ohlcv.overseas import YahooDailyChartService
from app.ohlcv.repository import OhlcvRepository
from app.ohlcv.schemas import DailyBarsResult, OhlcvCollectOptions, OhlcvScope
from app.notifications.collector import IssueEventRecorder, safe_record_issue
from app.notifications.models import IssueEvent, IssueKind


app_settings = container.settings()
configure_sentry(app_settings, SentryRuntime.SCRIPT)
configure_logging(app_settings)
logger = get_logger(__name__)


def build_options(argv: Sequence[str]) -> OhlcvCollectOptions:
    """명령행 인자로 실행 옵션을 만든다.

    Args:
        argv: 프로그램 이름을 제외한 명령행 인자.
            `[scope] [backfill | start [end]]` 형식이며 전부 생략할 수 있다.

    Returns:
        수집 실행 옵션. 기간을 주지 않으면 최근 구간, `backfill`이면 기준 시작일
        `BACKFILL_START`부터 오늘까지를 수집한다.

    Raises:
        ValueError: 범위 값이나 날짜 형식이 올바르지 않거나 인자가 너무 많은 경우.
    """

    arguments = list(argv)
    scope = OhlcvScope.ALL
    if arguments and arguments[0] in {member.value for member in OhlcvScope}:
        scope = OhlcvScope(arguments.pop(0))

    if not arguments:
        return OhlcvCollectOptions(scope=scope)
    if arguments[0] == BACKFILL_KEYWORD:
        return OhlcvCollectOptions(scope=scope, start=BACKFILL_START)
    if len(arguments) > 2:
        raise ValueError("period takes start and optional end (YYYY-MM-DD)")

    return OhlcvCollectOptions(
        scope=scope,
        start=date.fromisoformat(arguments[0]),
        end=date.fromisoformat(arguments[1]) if len(arguments) == 2 else None,
    )


@inject
async def main(
    options: OhlcvCollectOptions,
    korea_service: Annotated[
        KISKoreaDailyChartService,
        Provide[Container.korea_daily_chart_service],
    ],
    overseas_service: Annotated[
        YahooDailyChartService,
        Provide[Container.overseas_daily_chart_service],
    ],
    instrument_repository: Annotated[
        InstrumentRepository,
        Provide[Container.instrument_repository],
    ],
    repository: Annotated[
        OhlcvRepository,
        Provide[Container.ohlcv_repository],
    ],
    database: Annotated[
        Database,
        Provide[Container.database],
    ],
    issue_collector: Annotated[
        IssueEventRecorder,
        Provide[Container.issue_collector],
    ],
    scheduled: bool = False,
) -> None:
    """추적 종목의 확정 일봉을 수집해 DB에 저장한다.

    Args:
        options: 수집 범위와 기간 옵션.
        korea_service: 국내 일봉 수집 서비스.
        overseas_service: 해외 일봉 수집 서비스.
        instrument_repository: 추적 종목 조회 repository.
        repository: 수집 결과를 저장할 repository.
        database: 종료 시 정리할 데이터베이스 자원.
        issue_collector: 운영 이슈 이벤트 기록기.
        scheduled: Celery 정기 실행 여부.
    """

    # ts가 dedupe 키라 snapshot_ts는 눈금을 맞출 필요가 없다.
    snapshot_ts = utc_now()
    try:
        instruments = [
            instrument
            for instrument in await instrument_repository.list_watched()
            if instrument.market in options.scope.markets
        ]

        # 종목 하나를 받을 때마다 저장한다. 백필은 수십 분씩 도는데 마지막에 한 번만
        # 저장하면 중간에 한 종목이 실패했을 때 앞서 받은 것까지 전부 버려진다.
        saved = 0
        collected: list[datetime] = []
        async with httpx.AsyncClient() as client:
            for instrument in instruments:
                start, end = options.period(instrument.market, snapshot_ts)
                result = await _collect(
                    instrument,
                    start,
                    end,
                    korea_service,
                    overseas_service,
                    client,
                )
                saved += await repository.save_daily([result], snapshot_ts)
                collected.extend(bar.event_ts for bar in result.bars)

        # 소스가 요청 시작일부터 주지 못하면 있는 만큼만 담긴다. 어디부터 담겼는지는
        # first_ts로만 드러나므로 백필 로그에 함께 남긴다.
        collected.sort()
        logger.info(
            "ohlcv_daily_collected",
            scope=options.scope.value,
            instruments=len(instruments),
            fetched=len(collected),
            saved=saved,
            first_ts=collected[0].isoformat() if collected else "",
            last_ts=collected[-1].isoformat() if collected else "",
            snapshot_ts=snapshot_ts.isoformat(),
        )
        if scheduled and options.start is None and instruments and not collected:
            await safe_record_issue(
                issue_collector,
                IssueEvent.create(
                    kind=IssueKind.EMPTY_RESULT,
                    service="ohlcv",
                    operation=f"collect_{options.scope.value}_daily",
                    stable_dimension=options.scope.value,
                    summary="Scheduled OHLCV collection returned no bars.",
                    metric_name="fetched",
                    observed_value=0,
                    expected_value=1,
                    context={"scope": options.scope.value, "fetched": 0},
                ),
            )
    finally:
        await database.dispose()


async def _collect(
    instrument: Instrument,
    start: date,
    end: date,
    korea_service: KISKoreaDailyChartService,
    overseas_service: YahooDailyChartService,
    client: httpx.AsyncClient,
) -> DailyBarsResult:
    """종목 유형과 시장에 맞는 소스로 일봉을 수집한다.

    KIS 종목 시세 TR은 체결가가 있는 대상만 받는다. 국내 지수(KOSPI)는 시장이 KRX여도
    이 TR로 조회할 수 없어 Yahoo 지수 심볼(`^KS11`)로 우회한다.

    Args:
        instrument: 수집 대상 추적 종목.
        start: 조회 시작일.
        end: 조회 종료일.
        korea_service: 국내 일봉 수집 서비스.
        overseas_service: 해외·지수 일봉 수집 서비스.
        client: 국내 수집에 사용할 비동기 HTTP 클라이언트.

    Returns:
        해당 종목의 일봉 수집 결과. 0봉이면 경고 로그를 남긴다.
    """

    if instrument.market is Market.KRX and instrument.kind is not InstrumentKind.INDEX:
        result = await korea_service.collect_daily(instrument.ticker, start, end, client)
    else:
        result = await overseas_service.collect_daily(
            instrument.ticker,
            instrument.market,
            start,
            end,
            symbol=instrument.collect_symbol,
        )

    if not result.bars:
        # 휴장만 걸린 구간이면 정상이지만, 심볼·유형을 잘못 등록해도 같은 모양이라
        # 0봉은 항상 드러내 놓는다. 조용히 넘어가면 그 종목만 영영 비어 있는다.
        logger.warning(
            "ohlcv_instrument_returned_no_bars",
            ticker=instrument.ticker,
            symbol=instrument.collect_symbol,
            kind=instrument.kind.value,
            market=instrument.market.value,
            start=start.isoformat(),
            end=end.isoformat(),
        )
    return result


container.wire(modules=[sys.modules[__name__]], warn_unresolved=True)


if __name__ == "__main__":
    try:
        asyncio.run(main(build_options(sys.argv[1:])))
    finally:
        flush_sentry()

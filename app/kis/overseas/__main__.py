"""독립 미국주식 프로세스 엔트리포인트."""

import asyncio
import sys
from typing import Annotated

from dependency_injector.wiring import Provide, inject
from sqlalchemy.exc import SQLAlchemyError

from app.core.containers import Container, container
from app.core.database import Database
from app.core.logging import configure_logging, get_logger
from app.core.sentry import SentryRuntime, configure_sentry, flush_sentry
from app.core.models import utc_now
from app.instruments.models import Market
from app.instruments.repository import InstrumentRepository
from app.kis.overseas.quote import KISOverseasWebSocketQuote
from app.kis.overseas.repository import KISOverseasTickRepository
from app.kis.overseas.schemas import (
    KISOverseasMarket,
    KISOverseasSubscription,
    KISOverseasTrId,
)

app_settings = container.settings()
configure_sentry(app_settings, SentryRuntime.SCRIPT)
configure_logging(app_settings)
logger = get_logger(__name__)

KIS_MARKET_BY_INSTRUMENT_MARKET: dict[Market, KISOverseasMarket] = {
    Market.NASDAQ: KISOverseasMarket.NASDAQ,
    Market.NYSE: KISOverseasMarket.NYSE,
    Market.NYSE_ARCA: KISOverseasMarket.AMEX,
}


@inject
async def main(
    quote: Annotated[
        KISOverseasWebSocketQuote,
        Provide[Container.overseas_websocket_quote],
    ],
    repository: Annotated[
        KISOverseasTickRepository,
        Provide[Container.overseas_tick_repository],
    ],
    instrument_repository: Annotated[
        InstrumentRepository,
        Provide[Container.instrument_repository],
    ],
    database: Annotated[
        Database,
        Provide[Container.database],
    ],
) -> None:
    """미국주식 실시간 시세를 수신해 DB에 저장한다."""

    try:
        watched_instruments = await instrument_repository.list_watched()
        subscribed = 0
        skipped = 0
        for instrument in watched_instruments:
            kis_market = KIS_MARKET_BY_INSTRUMENT_MARKET.get(instrument.market)
            if kis_market is None:
                # 국내·지수·환율·선물은 KIS 해외주식 실시간 대상이 아니다. 다만 매핑을
                # 빠뜨려도 같은 모양이라(실제로 NYSE가 빠져 TSM이 조용히 누락됐었다)
                # 건너뛴 대상을 남긴다.
                skipped += 1
                logger.info(
                    "kis_tick_market_not_subscribable",
                    market="overseas",
                    ticker=instrument.ticker,
                    instrument_market=instrument.market.value,
                )
                continue

            for tr_id in (
                KISOverseasTrId.TRADE,
                KISOverseasTrId.ORDERBOOK,
            ):
                await quote.subscribe(
                    KISOverseasSubscription(
                        code=instrument.ticker,
                        market=kis_market,
                        tr_id=tr_id,
                    )
                )
            subscribed += 1

        # 추적 종목이 늘었는데 구독이 늘지 않는 상태가 로그로 드러나야 한다.
        logger.info(
            "kis_tick_subscriptions_ready",
            market="overseas",
            watched=len(watched_instruments),
            subscribed=subscribed,
            skipped=skipped,
        )

        async with asyncio.TaskGroup() as task_group:
            task_group.create_task(quote.run())
            async for message in quote.stream():
                received_at = utc_now()
                try:
                    await repository.save(message, received_at)
                except SQLAlchemyError:
                    logger.exception(
                        "kis_tick_persist_failed",
                        market="overseas",
                        symbol=message.symbol,
                        tick_type=type(message).__name__,
                        received_at=received_at.isoformat(),
                    )
                    continue

                logger.info(
                    "kis_tick_saved",
                    market="overseas",
                    symbol=message.symbol,
                    tick_type=type(message).__name__,
                    received_at=received_at.isoformat(),
                )
    finally:
        await database.dispose()


container.wire(modules=[sys.modules[__name__]], warn_unresolved=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        flush_sentry()

"""독립 미국주식 프로세스 엔트리포인트."""

import asyncio
import sys
from typing import Annotated

from dependency_injector.wiring import Provide, inject
from sqlalchemy.exc import SQLAlchemyError

from app.core.containers import Container, container
from app.core.database import Database
from app.core.logging import configure_logging, get_logger
from app.core.models import utc_now
from app.instruments.models import Market
from app.instruments.repository import InstrumentRepository
from app.kis.overseas.quote import KISOverseasWebSocketQuote
from app.kis.overseas.repository import KISOverseasTickRepository
from app.kis.overseas.schemas import (
    KISOverseasMarket,
    KISOverseasStockCode,
    KISOverseasSubscription,
    KISOverseasTrId,
)

configure_logging(container.settings())
logger = get_logger(__name__)

KIS_MARKET_BY_INSTRUMENT_MARKET: dict[Market, KISOverseasMarket] = {
    Market.NASDAQ: KISOverseasMarket.NASDAQ,
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
        for instrument in watched_instruments:
            kis_market = KIS_MARKET_BY_INSTRUMENT_MARKET.get(instrument.market)
            if kis_market is None:
                continue

            for tr_id in (
                KISOverseasTrId.TRADE,
                KISOverseasTrId.ORDERBOOK,
            ):
                await quote.subscribe(
                    KISOverseasSubscription(
                        code=KISOverseasStockCode(instrument.ticker),
                        market=kis_market,
                        tr_id=tr_id,
                    )
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
    asyncio.run(main())

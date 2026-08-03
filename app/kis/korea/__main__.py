"""독립 한국주식 프로세스 엔트리포인트."""

import asyncio
import sys
from typing import Annotated

from dependency_injector.wiring import Provide, inject
from sqlalchemy.exc import SQLAlchemyError

from app.core.containers import Container, container
from app.core.database import Database
from app.core.logging import configure_logging, get_logger
from app.core.models import utc_now
from app.instruments.models import InstrumentKind, Market
from app.instruments.repository import InstrumentRepository
from app.kis.korea.quote import KISKoreaWebSocketQuote
from app.kis.korea.repository import KISKoreaTickRepository
from app.kis.korea.schemas import (
    KISKoreaSubscription,
    KISKoreaTrId,
)

configure_logging(container.settings())
logger = get_logger(__name__)


@inject
async def main(
    quote: Annotated[
        KISKoreaWebSocketQuote,
        Provide[Container.korea_websocket_quote],
    ],
    repository: Annotated[
        KISKoreaTickRepository,
        Provide[Container.korea_tick_repository],
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
    """한국주식 실시간 시세를 수신해 DB에 저장한다."""

    try:
        watched_instruments = await instrument_repository.list_watched()
        subscribed = 0
        skipped = 0
        for instrument in watched_instruments:
            # 지수(KOSPI)는 시장이 KRX여도 체결가가 없어 실시간 체결·호가 TR로 받을 수 없다.
            # 구독을 시도하면 KIS가 거절하고 그 예외가 이 프로세스를 죽인다. 일봉은
            # app.ohlcv가 Yahoo 지수 심볼로 따로 받는다.
            if instrument.market is not Market.KRX or instrument.kind is InstrumentKind.INDEX:
                skipped += 1
                continue

            for tr_id in (
                KISKoreaTrId.STOCK_TRADE_KRX,
                KISKoreaTrId.STOCK_ORDERBOOK_KRX,
            ):
                await quote.subscribe(
                    KISKoreaSubscription(
                        code=instrument.ticker,
                        tr_id=tr_id,
                    )
                )
            subscribed += 1

        # 추적 종목이 늘었는데 구독이 늘지 않는 상태가 로그로 드러나야 한다.
        logger.info(
            "kis_tick_subscriptions_ready",
            market="korea",
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
                        market="korea",
                        stock_code=message.stock_code,
                        tick_type=type(message).__name__,
                        received_at=received_at.isoformat(),
                    )
                    continue

                logger.info(
                    "kis_tick_saved",
                    market="korea",
                    stock_code=message.stock_code,
                    tick_type=type(message).__name__,
                    received_at=received_at.isoformat(),
                )
    finally:
        await database.dispose()


container.wire(modules=[sys.modules[__name__]], warn_unresolved=True)


if __name__ == "__main__":
    asyncio.run(main())

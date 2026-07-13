"""독립 미국주식 프로세스 엔트리포인트."""

import asyncio
import logging

from app.core.config import settings
from app.kis.auth import KISAuth
from app.kis.overseas.quote import KISOverseasWebSocketQuote
from app.kis.overseas.schemas import (
    KISOverseasMarket,
    KISOverseasStockCode,
    KISOverseasSubscription,
    KISOverseasTrId,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    """승인 키를 발급하고 미국주식 실시간 시세를 수신한다."""

    token = await KISAuth(settings).get_websocket_token()
    quote = KISOverseasWebSocketQuote(settings=settings, token=token)
    await quote.subscribe(
        KISOverseasSubscription(
            code=KISOverseasStockCode.APPLE,
            market=KISOverseasMarket.NASDAQ,
            tr_id=KISOverseasTrId.TRADE,
        )
    )

    async with asyncio.TaskGroup() as task_group:
        task_group.create_task(quote.run())
        async for message in quote.stream():
            logger.info("tick: %s", message)


if __name__ == "__main__":
    asyncio.run(main())

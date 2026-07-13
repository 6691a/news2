"""독립 한국주식 프로세스 엔트리포인트."""

import asyncio
import logging

from app.core.config import settings
from app.kis.auth import KISAuth
from app.kis.korea.quote import KISKoreaWebSocketQuote
from app.kis.korea.schemas import (
    KISKoreaStockCode,
    KISKoreaSubscription,
    KISKoreaTrId,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    """승인 키를 발급하고 한국주식 실시간 시세를 수신한다."""

    token = await KISAuth(settings).get_websocket_token()
    quote = KISKoreaWebSocketQuote(settings=settings, token=token)
    await quote.subscribe(
        KISKoreaSubscription(
            code=KISKoreaStockCode.SAMSUNG_ELECTRONICS,
            tr_id=KISKoreaTrId.STOCK_TRADE_KRX,
        )
    )

    async with asyncio.TaskGroup() as task_group:
        task_group.create_task(quote.run())
        async for message in quote.stream():
            logger.info("tick: %s", message)


if __name__ == "__main__":
    asyncio.run(main())

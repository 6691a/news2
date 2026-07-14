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
        # TODO(사용자): quote.stream()이 typed DTO stream이 되면 이 루프를 갱신한다.
        #  1차: DTO 필드 로깅 (예: event.stock_code, event.current_price) +
        #       KISKoreaTickRepository로 건별 저장 (isinstance로 Trade/Orderbook 분기).
        #       저장 실패(DB 다운 등)는 로그 후 폐기 — 재시도 큐는 과잉.
        #  2차(선택): N건 또는 T초마다 flush하는 버퍼링으로 리팩터.
        async for message in quote.stream():
            logger.info("tick: %s", message)


if __name__ == "__main__":
    asyncio.run(main())

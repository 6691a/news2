"""독립 프로세스 엔트리포인트: KIS 실시간 시세를 수신한다.

Docker Compose에서 `python -m app.kis`로 실행하며 `restart: always`가 감독한다.
치명 오류(잘못된 토큰·URI 등)는 `run()`이 전파하므로 프로세스가 비정상 종료되고
Docker가 새로 띄운다. 일시적 끊김은 `run()` 내부에서 재연결로 흡수된다.
"""

import asyncio
import logging

from app.core.config import settings
from app.kis.auth import KISAuth
from app.kis.quote import KISWebSocketQuote
from app.kis.schemas import StockCode

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    """승인 키를 발급받아 실시간 시세를 구독하고 수신 루프를 돌린다."""

    token = await KISAuth(settings).get_websocket_token()
    quote = KISWebSocketQuote(settings=settings, token=token)

    # TODO: 구독할 종목을 필요에 맞게 조정한다.
    await quote.subscribe(StockCode.SAMSUNG_ELECTRONICS)

    async with asyncio.TaskGroup() as tg:
        tg.create_task(quote.run())  # 치명 오류 시 전파 → 프로세스 종료
        async for message in quote.stream():
            # TODO: 파싱·저장 등 실제 처리로 대체한다.
            logger.info("tick: %s", message)


if __name__ == "__main__":
    # 예외가 밖으로 나가면 종료 코드 != 0 → Docker restart.
    asyncio.run(main())

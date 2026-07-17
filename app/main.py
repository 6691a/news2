from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.containers import container
from app.core.logging import configure_logging


configure_logging(container.settings())


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """애플리케이션 시작 시 DB 연결을 확인하고 종료 시 연결 풀을 정리한다.

    Args:
        app: 수명주기를 적용할 FastAPI 애플리케이션.

    Yields:
        DB 연결 확인이 끝난 애플리케이션 실행 구간.
    """
    database = container.database()
    try:
        await database.check_connection()
        yield
    finally:
        await database.dispose()


app = FastAPI(title="News2", lifespan=lifespan)
app.container = container

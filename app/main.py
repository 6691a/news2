from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.containers import container
from app.core.logging import configure_logging
from app.core.sentry import SentryRuntime, configure_sentry


app_settings = container.settings()
configure_sentry(app_settings, SentryRuntime.FASTAPI)
configure_logging(app_settings)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """애플리케이션 시작 때 DB 연결을 확인하고 종료 때 연결 자원을 정리한다.

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

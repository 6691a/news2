"""SQLAlchemy 비동기 데이터베이스 연결을 관리한다."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """News2 ORM 모델의 공용 declarative base."""


class Database:
    """SQLAlchemy 비동기 엔진과 세션 팩토리의 수명주기를 관리한다."""

    def __init__(self, database_url: str) -> None:
        """데이터베이스 URL로 비동기 엔진과 세션 팩토리를 생성한다.

        Args:
            database_url: SQLAlchemy 비동기 PostgreSQL 연결 URL.
        """
        self.engine: AsyncEngine = create_async_engine(
            database_url,
            pool_pre_ping=True,
            connect_args={"server_settings": {"timezone": "UTC"}},
        )
        self.session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
        )

    async def check_connection(self) -> None:
        """간단한 쿼리로 데이터베이스 연결 가능 여부를 확인한다."""
        async with self.engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

    async def dispose(self) -> None:
        """비동기 엔진의 연결 풀을 종료한다."""
        await self.engine.dispose()

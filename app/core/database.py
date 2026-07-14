"""SQLAlchemy 비동기 데이터베이스 연결을 관리한다."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

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
        )
        self.session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
        )

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """독립 세션을 열고 작업 결과에 따라 트랜잭션을 정리한다.

        Yields:
            호출 작업에만 사용되는 비동기 세션.

        Raises:
            BaseException: 작업 중 발생한 원래 예외를 rollback 후 다시 발생시킨다.
        """
        session = self.session_factory()
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def check_connection(self) -> None:
        """간단한 쿼리로 데이터베이스 연결 가능 여부를 확인한다."""
        async with self.engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

    async def dispose(self) -> None:
        """비동기 엔진의 연결 풀을 종료한다."""
        await self.engine.dispose()

"""추적 종목을 조회하는 SQLAlchemy repository."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.instruments.models import Instrument


class InstrumentRepository:
    """추적 종목 조회를 담당하는 repository."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """비동기 세션 팩토리를 주입받는다.

        Args:
            session_factory: 작업 단위마다 세션을 만드는 SQLAlchemy 팩토리.
        """

        self._session_factory = session_factory

    async def list_watched(self) -> list[Instrument]:
        """현재 수집·분석 대상으로 설정된 종목을 반환한다.

        Returns:
            내부 식별자 순으로 정렬된 추적 종목 목록.
        """

        statement = select(Instrument).where(Instrument.is_watched.is_(True)).order_by(Instrument.id)
        async with self._session_factory() as session:
            result = await session.scalars(statement)
            return list(result.all())

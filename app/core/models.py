"""모든 SQLAlchemy 엔티티가 공유하는 컬럼과 UTC 시간 타입."""

from datetime import UTC, datetime

from sqlalchemy import BigInteger, DateTime, func
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from app.core.database import Base


def utc_now() -> datetime:
    """현재 시각을 timezone-aware UTC datetime으로 반환한다."""
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    """입력과 출력 datetime을 항상 timezone-aware UTC로 정규화한다."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(
        self,
        value: datetime | None,
        dialect: Dialect,
    ) -> datetime | None:
        """DB 저장 전 datetime을 UTC로 변환한다.

        Args:
            value: 저장할 datetime 또는 None.
            dialect: SQLAlchemy가 사용하는 DB dialect.

        Returns:
            UTC로 변환된 timezone-aware datetime 또는 None.

        Raises:
            ValueError: timezone 정보가 없는 naive datetime인 경우.
        """
        del dialect
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("UTCDateTime requires a timezone-aware datetime")
        return value.astimezone(UTC)

    def process_result_value(
        self,
        value: datetime | None,
        dialect: Dialect,
    ) -> datetime | None:
        """DB 조회 결과를 timezone-aware UTC datetime으로 변환한다.

        Args:
            value: DB가 반환한 datetime 또는 None.
            dialect: SQLAlchemy가 사용하는 DB dialect.

        Returns:
            UTC로 변환된 timezone-aware datetime 또는 None.
        """
        del dialect
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class EntityModel(Base):
    """식별자와 UTC 생성·수정 시각을 제공하는 추상 ORM 모델."""

    __abstract__ = True

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="엔티티 내부 식별자",
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
        comment="레코드가 생성된 UTC 시각",
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
        server_onupdate=func.now(),
        comment="레코드가 마지막으로 수정된 UTC 시각",
    )

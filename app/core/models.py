"""모든 SQLAlchemy 엔티티가 공유하는 컬럼과 UTC 시간 타입."""

from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import BigInteger, DateTime, func
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from app.core.database import Base


def utc_now() -> datetime:
    """현재 시각을 timezone-aware UTC datetime으로 반환한다."""
    return datetime.now(UTC)


def enum_column(enum_type: type[Enum], *, name: str) -> SQLAlchemyEnum:
    """Enum을 저장하는 컬럼 타입을 프로젝트 공통 규칙으로 만든다.

    네이티브 PostgreSQL ENUM 타입 대신 VARCHAR + CHECK 제약을 쓰고, 멤버 이름이 아니라
    멤버 값을 저장한다. 멤버를 늘리거나 줄일 때 타입 변경 없이 CHECK 제약만 갱신하면 된다.

    호출할 때마다 새 인스턴스를 반환한다. 반환값은 컬럼 하나에 귀속되는 SchemaType이므로
    모듈 상수로 만들어 여러 컬럼에서 공유하지 않는다.

    Args:
        enum_type: 컬럼에 저장할 파이썬 Enum 클래스.
        name: CHECK 제약에 쓰일 이름. 테이블 안에서 유일해야 한다.

    Returns:
        native_enum=False, create_constraint=True, validate_strings=True가 적용되고
        멤버 값을 저장하도록 설정된 SQLAlchemy Enum 타입.
    """
    return SQLAlchemyEnum(
        enum_type,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda enum: [member.value for member in enum],
    )


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

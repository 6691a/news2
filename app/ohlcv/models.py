"""추적 종목 OHLCV SQLAlchemy 모델."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import EntityModel, UTCDateTime, enum_column
from app.ohlcv.schemas import Timeframe


class Ohlcv(EntityModel):
    """종목별 봉 데이터를 timeframe 하나로 구분해 담는다.

    확정 일봉('1d')과 장중 분봉('1m')이 소스·그레인만 다르고 컬럼이 같아 한 테이블을
    공유한다. 실시간 tick 테이블과 달리 여기 들어가는 값은 소스가 확정한 봉이다.
    """

    __tablename__ = "ohlcv"
    __table_args__ = (
        UniqueConstraint(
            "instrument_id",
            "timeframe",
            "ts",
            name="uq_ohlcv_instrument_timeframe_ts",
        ),
        # 조회는 (종목, 봉간격, 기간) 순으로만 들어오므로 UNIQUE 제약이 만드는
        # btree 인덱스가 그대로 조회 인덱스다. 별도 인덱스를 만들지 않는다.
        {"comment": "추적 종목의 확정 일봉과 장중 분봉"},
    )

    instrument_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("instruments.id", ondelete="RESTRICT"),
        nullable=False,
        comment="봉이 속한 추적 종목",
    )
    timeframe: Mapped[Timeframe] = mapped_column(
        enum_column(Timeframe, name="ohlcv_timeframe"),
        nullable=False,
        comment="봉 간격. 1d=확정 일봉, 1m=장중 분봉",
    )
    ts: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        comment="봉이 시작한 UTC 시각. 일봉은 거래소 현지 00:00에 대응한다",
    )
    open: Mapped[Decimal] = mapped_column(
        Numeric(28, 8),
        nullable=False,
        comment="시가",
    )
    high: Mapped[Decimal] = mapped_column(
        Numeric(28, 8),
        nullable=False,
        comment="고가",
    )
    low: Mapped[Decimal] = mapped_column(
        Numeric(28, 8),
        nullable=False,
        comment="저가",
    )
    close: Mapped[Decimal] = mapped_column(
        Numeric(28, 8),
        nullable=False,
        comment="종가. 국내는 KIS 수정주가, 해외는 Yahoo 배당·분할 조정가",
    )
    volume: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="봉 구간 거래량(주)",
    )
    snapshot_ts: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        comment="응답을 수신한 UTC 시각. 수정주가 소급 반영 시 갱신된다",
    )

"""미국 국채 수익률·국채선물 SQLAlchemy 모델."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import EntityModel, UTCDateTime, enum_column
from app.macro.us_treasury.schemas import TreasurySeries


class UsTreasuryBar(EntityModel):
    """수익률(^TNX)과 국채선물(ZN=F)의 장중 1분봉을 한 테이블에 담는다.

    두 계열은 소스·파싱·그레인·저장 로직이 같고 값의 단위만 다르다. 단위 구분은
    series가 담당한다: US10Y는 수익률 %, ZN은 가격 포인트다.
    """

    __tablename__ = "us_treasury_bars"
    __table_args__ = (
        UniqueConstraint(
            "series",
            "event_ts",
            name="uq_us_treasury_bars_series_event_ts",
        ),
        {"comment": "미국 국채 수익률(^TNX)·국채선물 가격(ZN=F) 장중 1분봉 (Yahoo)"},
    )

    series: Mapped[TreasurySeries] = mapped_column(
        enum_column(TreasurySeries, name="us_treasury_series"),
        nullable=False,
        comment="국채 계열. US10Y=10년물 수익률, ZN=10년물 국채선물",
    )
    event_ts: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        comment="봉이 시작한 UTC 시각",
    )
    open: Mapped[Decimal | None] = mapped_column(
        Numeric(16, 8),
        nullable=True,
        comment="시가. US10Y=수익률 %, ZN=가격 포인트",
    )
    high: Mapped[Decimal | None] = mapped_column(
        Numeric(16, 8),
        nullable=True,
        comment="고가. US10Y=수익률 %, ZN=가격 포인트",
    )
    low: Mapped[Decimal | None] = mapped_column(
        Numeric(16, 8),
        nullable=True,
        comment="저가. US10Y=수익률 %, ZN=가격 포인트",
    )
    close: Mapped[Decimal] = mapped_column(
        Numeric(16, 8),
        nullable=False,
        comment="종가. US10Y=수익률 %, ZN=가격 포인트(1/64 분수)",
    )
    snapshot_ts: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        comment="응답을 수신한 UTC 시각",
    )


class UsTreasuryYieldDaily(EntityModel):
    """연준 H.15(FRED DGS10) 일별 확정 수익률."""

    __tablename__ = "us_treasury_yield_daily"
    __table_args__ = (
        UniqueConstraint(
            "series",
            "observation_date",
            name="uq_us_treasury_yield_daily_series_observation_date",
        ),
        {"comment": "미국 국채 수익률 일별 확정치 (FRED H.15)"},
    )

    series: Mapped[TreasurySeries] = mapped_column(
        enum_column(TreasurySeries, name="us_treasury_series"),
        nullable=False,
        comment="국채 계열. 확정치는 US10Y만 존재한다",
    )
    observation_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        comment="확정치 기준 미 동부(ET) 영업일",
    )
    yield_pct: Mapped[Decimal] = mapped_column(
        Numeric(8, 4),
        nullable=False,
        comment="H.15 CMT 수익률(%)",
    )
    snapshot_ts: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        comment="응답을 수신한 UTC 시각",
    )

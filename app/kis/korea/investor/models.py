"""국내 투자자 수급 SQLAlchemy 모델."""

from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, ForeignKey, Index, Text, UniqueConstraint
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import EntityModel, UTCDateTime
from app.kis.korea.investor.schemas import InvestorFlowVenue, InvestorType
from app.kis.korea.models import JSON_DOCUMENT


class InvestorFlow(EntityModel):
    """투자자 유형별 순매수를 long-format 한 행으로 저장한다.

    KIS 응답 1건(TR 1회 호출)은 투자자 유형 수 x 시간대 수만큼의 행으로 펼쳐진다.
    - 종목 장중(HHPTJ04160200): 외국인/기관 2종 x 시간대 4종 = 8행
    - 시장 장중(FHPTJ04030000): 투자자 12종 x 1 = 12행 (미집계 유형은 제외)
    - 종목 마감(FHPTJ04160001): 투자자 12종 x 1 = 12행 (venue별로 따로 호출)
    - 시장 마감(FHPTJ04040000): 투자자 12종 x 1 = 12행
    """

    __tablename__ = "investor_flows"
    __table_args__ = (
        UniqueConstraint(
            "instrument_id",
            "trade_date",
            "investor_type",
            "venue",
            "time_bucket",
            "is_provisional",
            "snapshot_ts",
            name="uq_investor_flows_snapshot",
        ),
        Index(
            "ix_investor_flows_instrument_id_trade_date",
            "instrument_id",
            "trade_date",
        ),
        {"comment": "KIS 국내 투자자별 순매수 동향"},
    )

    instrument_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("instruments.id"),
        nullable=False,
        comment="수급 대상 종목 또는 시장 instrument",
    )
    trade_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        comment="수급 기준 영업일(한국 날짜)",
    )
    venue: Mapped[InvestorFlowVenue] = mapped_column(
        SQLAlchemyEnum(
            InvestorFlowVenue,
            name="investor_flow_venue",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            # 멤버 이름이 아니라 값을 저장한다.
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
        comment="응답의 거래 시장 범위",
    )
    investor_type: Mapped[InvestorType] = mapped_column(
        SQLAlchemyEnum(
            InvestorType,
            name="investor_flow_investor_type",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            # 멤버 이름이 아니라 값을 저장한다.
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
        comment="투자자 유형",
    )
    net_buy_volume: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment="순매수 수량(주)",
    )
    net_buy_value: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment="순매수 거래대금(백만원, KIS 원본 단위). 금액을 주지 않는 TR은 NULL",
    )
    time_bucket: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default="",
        comment="장중 집계 시간대 구분. 구분이 없으면 빈 문자열",
    )
    is_provisional: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        comment="장중 가집계(잠정치) 여부",
    )
    snapshot_ts: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        comment="응답을 수신한 UTC 시각",
    )
    details: Mapped[dict[str, object]] = mapped_column(
        JSON_DOCUMENT,
        nullable=False,
        comment="매도·매수 원본 등 순매수 외 필드",
    )

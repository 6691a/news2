"""해외주식 실시간 체결과 호가 SQLAlchemy 모델."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Date,
    Index,
    JSON,
    Numeric,
    SmallInteger,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import EntityModel, UTCDateTime, utc_now


JSON_DOCUMENT = JSON().with_variant(JSONB(), "postgresql")


class OverseasTrade(EntityModel):
    """해외주식 실시간 체결 tick을 저장한다."""

    __tablename__ = "overseas_trades"
    __table_args__ = (
        Index("ix_overseas_trades_symbol_event_ts", "symbol", "event_ts"),
        {"comment": "KIS 해외주식 실시간 체결 tick"},
    )

    realtime_symbol: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="시세 구분과 거래소 및 티커가 결합된 KIS 실시간 종목코드",
    )
    symbol: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="해외주식 종목 티커",
    )
    market: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="구독 정보에서 확인한 KIS 해외 거래소 코드",
    )
    event_ts: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        comment="한국 일자와 시간을 결합해 변환한 UTC 체결 시각",
    )
    local_business_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        comment="거래소 현지 영업일자",
    )
    decimal_places: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        comment="가격 표시에 사용하는 소수점 자리수",
    )
    price: Mapped[Decimal] = mapped_column(
        Numeric(28, 8),
        nullable=False,
        comment="해외주식 현재가 기준 체결 가격",
    )
    volume: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="직전 체결 수량",
    )
    cumulative_volume: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="현지 영업일 누적 거래량",
    )
    cumulative_amount: Mapped[Decimal] = mapped_column(
        Numeric(28, 8),
        nullable=False,
        comment="현지 영업일 누적 거래대금",
    )
    best_bid_price: Mapped[Decimal] = mapped_column(
        Numeric(28, 8),
        nullable=False,
        comment="체결 수신 시점의 최우선 매수호가",
    )
    best_ask_price: Mapped[Decimal] = mapped_column(
        Numeric(28, 8),
        nullable=False,
        comment="체결 수신 시점의 최우선 매도호가",
    )
    best_bid_quantity: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="체결 수신 시점의 최우선 매수호가 잔량",
    )
    best_ask_quantity: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="체결 수신 시점의 최우선 매도호가 잔량",
    )
    trade_strength: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8),
        nullable=True,
        comment="매수와 매도 체결량을 이용한 체결강도",
    )
    market_type: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="KIS 체결 응답의 시장 구분 코드",
    )
    details: Mapped[dict[str, object]] = mapped_column(
        JSON_DOCUMENT,
        nullable=False,
        comment="시가와 등락률 등 비핵심 체결 DTO 필드",
    )
    received_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
        comment="애플리케이션이 체결 tick을 수신한 UTC 시각",
    )


class OverseasOrderbook(EntityModel):
    """해외주식 실시간 10단계 호가 스냅샷을 저장한다."""

    __tablename__ = "overseas_orderbooks"
    __table_args__ = (
        Index(
            "ix_overseas_orderbooks_symbol_event_ts",
            "symbol",
            "event_ts",
        ),
        {"comment": "KIS 해외주식 실시간 10단계 호가 스냅샷"},
    )

    realtime_symbol: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="시세 구분과 거래소 및 티커가 결합된 KIS 실시간 종목코드",
    )
    symbol: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="해외주식 종목 티커",
    )
    market: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="구독 정보에서 확인한 KIS 해외 거래소 코드",
    )
    event_ts: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        comment="한국 일자와 시간을 결합해 변환한 UTC 호가 시각",
    )
    decimal_places: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        comment="가격 표시에 사용하는 소수점 자리수",
    )
    best_bid_price: Mapped[Decimal] = mapped_column(
        Numeric(28, 8),
        nullable=False,
        comment="1단계 최우선 매수호가",
    )
    best_ask_price: Mapped[Decimal] = mapped_column(
        Numeric(28, 8),
        nullable=False,
        comment="1단계 최우선 매도호가",
    )
    best_bid_quantity: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="1단계 최우선 매수호가 잔량",
    )
    best_ask_quantity: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="1단계 최우선 매도호가 잔량",
    )
    total_bid_quantity: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="전체 매수호가 잔량",
    )
    total_ask_quantity: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="전체 매도호가 잔량",
    )
    levels: Mapped[list[dict[str, object]]] = mapped_column(
        JSON_DOCUMENT,
        nullable=False,
        comment="가격과 잔량 및 증감을 포함한 1단계부터 10단계까지의 호가 목록",
    )
    details: Mapped[dict[str, object]] = mapped_column(
        JSON_DOCUMENT,
        nullable=False,
        comment="총잔량 증감 등 비핵심 호가 DTO 필드",
    )
    received_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
        comment="애플리케이션이 호가 스냅샷을 수신한 UTC 시각",
    )

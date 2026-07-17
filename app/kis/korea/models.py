"""국내주식 실시간 체결과 호가 SQLAlchemy 모델."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Index, JSON, Numeric, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import EntityModel, UTCDateTime


JSON_DOCUMENT = JSON().with_variant(JSONB(), "postgresql")


class KoreaTrade(EntityModel):
    """국내주식 실시간 체결 tick을 저장한다."""

    __tablename__ = "korea_trades"
    __table_args__ = (
        Index("ix_korea_trades_stock_code_event_ts", "stock_code", "event_ts"),
        {"comment": "KIS 국내주식 실시간 체결 tick"},
    )

    stock_code: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="KIS 유가증권 단축 종목코드",
    )
    event_ts: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        comment="영업일자와 체결시각을 결합한 UTC 체결 시각",
    )
    price: Mapped[Decimal] = mapped_column(
        Numeric(28, 8),
        nullable=False,
        comment="주식 현재가 기준 체결 가격",
    )
    volume: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="직전 체결 수량",
    )
    cumulative_volume: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="영업일 누적 거래량",
    )
    cumulative_amount: Mapped[Decimal] = mapped_column(
        Numeric(28, 8),
        nullable=False,
        comment="영업일 누적 거래대금",
    )
    trade_strength: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8),
        nullable=True,
        comment="매수와 매도 체결량을 이용한 체결강도",
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
    trade_classification_code: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="KIS 체결 구분 코드",
    )
    details: Mapped[dict[str, object]] = mapped_column(
        JSON_DOCUMENT,
        nullable=False,
        comment="등락률과 장중 통계 등 비핵심 체결 DTO 필드",
    )
    received_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        server_default=func.now(),
        comment="애플리케이션이 체결 tick을 수신한 UTC 시각",
    )


class KoreaOrderbook(EntityModel):
    """국내주식 실시간 10단계 호가 스냅샷을 저장한다."""

    __tablename__ = "korea_orderbooks"
    __table_args__ = (
        Index(
            "ix_korea_orderbooks_stock_code_event_ts",
            "stock_code",
            "event_ts",
        ),
        {"comment": "KIS 국내주식 실시간 10단계 호가 스냅샷"},
    )

    stock_code: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="KIS 유가증권 단축 종목코드",
    )
    event_ts: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        comment="수신일자와 영업시각을 결합한 UTC 호가 시각",
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
        comment="가격과 잔량을 포함한 1단계부터 10단계까지의 호가 목록",
    )
    details: Mapped[dict[str, object]] = mapped_column(
        JSON_DOCUMENT,
        nullable=False,
        comment="예상체결과 시간외 잔량 등 비핵심 호가 DTO 필드",
    )
    received_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        server_default=func.now(),
        comment="애플리케이션이 호가 스냅샷을 수신한 UTC 시각",
    )

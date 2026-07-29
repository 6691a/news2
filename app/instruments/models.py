"""추적 종목의 기준 정보를 저장하는 SQLAlchemy 모델."""

from enum import StrEnum

from sqlalchemy import Boolean, Text, UniqueConstraint, true
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import EntityModel, enum_column


class Market(StrEnum):
    """추적 종목이 상장된 거래 시장."""

    KRX = "KRX"
    NASDAQ = "NASDAQ"
    NYSE_ARCA = "NYSE_ARCA"


class Instrument(EntityModel):
    """시세·뉴스·시그널이 참조할 추적 종목의 기준 정보를 저장한다."""

    __tablename__ = "instruments"
    __table_args__ = (
        UniqueConstraint(
            "ticker",
            "market",
            name="uq_instruments_ticker_market",
        ),
        {"comment": "시세·뉴스·시그널이 참조하는 추적 종목 마스터"},
    )
    ticker: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="거래 시장에서 사용하는 종목 코드",
    )
    market: Mapped[Market] = mapped_column(
        enum_column(Market, name="instrument_market"),
        nullable=False,
        comment="종목이 상장된 거래 시장",
    )
    name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="종목 표시 이름",
    )
    is_watched: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
        comment="신규 데이터 수집과 분석을 수행할 추적 대상 여부",
    )

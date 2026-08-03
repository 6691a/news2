"""추적 종목의 기준 정보를 저장하는 SQLAlchemy 모델."""

from enum import StrEnum

from sqlalchemy import Boolean, Text, UniqueConstraint, true
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import EntityModel, enum_column


class Market(StrEnum):
    """가격이 매겨지는 거래 세션.

    거래소 이름이 아니라 **시간대와 마감 시각이 같은 묶음**이다. 일봉의 거래일이
    현지 자정 기준이라 시간대를 틀리면 날짜가 하루 밀린다.
    """

    KRX = "KRX"
    NASDAQ = "NASDAQ"
    NYSE = "NYSE"
    NYSE_ARCA = "NYSE_ARCA"
    US_INDEX = "US_INDEX"  # 미국 지수. 특정 거래소 상장물이 아니라 따로 둔다
    JPX = "JPX"
    HKEX = "HKEX"
    SSE = "SSE"
    TWSE = "TWSE"
    GLOBEX = "GLOBEX"  # CME 선물·원자재
    FX = "FX"  # 24시간 외환


class InstrumentKind(StrEnum):
    """자산 유형.

    가격 소스를 가르는 데 쓰고(국내 지수는 종목 TR로 못 받는다), 분석 단계에서
    "지수만"·"환율만" 같은 필터의 근거도 된다.
    """

    EQUITY = "EQUITY"  # 개별주
    ETF = "ETF"  # 상장지수펀드. 거래되는 종목이라 개별주와 같은 소스를 쓴다
    INDEX = "INDEX"  # 계산 지수. 체결가가 없어 지수 전용 소스가 필요하다
    FX = "FX"  # 환율
    FUTURES = "FUTURES"  # 지수 선물(Yahoo 연속선물). 방향성만 보므로 월물을 따지지 않는다
    # 원자재 선물. KIS 해외선물의 거래량 기준 최근월물을 월물코드 단위로 등록한다.
    # Yahoo 연속선물은 롤 시점 가격이 이어 붙어 있어 쓰지 않는다(§1.5).
    COMMODITY = "COMMODITY"


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
    kind: Mapped[InstrumentKind] = mapped_column(
        enum_column(InstrumentKind, name="instrument_kind"),
        nullable=False,
        comment="가격 수집 소스를 가르는 유형",
    )
    source_symbol: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="수집 소스에서 쓰는 심볼. 티커와 다를 때만 채운다(예: KOSPI → ^KS11)",
    )
    is_watched: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
        comment="신규 데이터 수집과 분석을 수행할 추적 대상 여부",
    )

    @property
    def collect_symbol(self) -> str:
        """가격 수집 소스에 넘길 심볼.

        Returns:
            `source_symbol`이 있으면 그 값, 없으면 티커.
        """

        return self.source_symbol or self.ticker

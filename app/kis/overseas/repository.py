"""해외주식 실시간 DTO를 ORM 모델로 변환하고 저장한다."""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core._time import kst_datetime
from app.kis.overseas.models import OverseasOrderbook, OverseasTrade
from app.kis.overseas.schemas import KISOverseasOrderbook, KISOverseasTrade


OVERSEAS_TRADE_DETAIL_EXCLUDES = {
    "realtime_symbol",
    "symbol",
    "decimal_places",
    "local_business_date",
    "last_price",
    "trade_volume",
    "total_volume",
    "total_amount",
    "bid_price",
    "ask_price",
    "bid_quantity",
    "ask_quantity",
    "trade_strength",
    "market_type",
}
OVERSEAS_ORDERBOOK_DETAIL_EXCLUDES = {
    "realtime_symbol",
    "symbol",
    "decimal_places",
    "levels",
    "total_bid_quantity",
    "total_ask_quantity",
}


def _market_from_realtime_symbol(realtime_symbol: str) -> str:
    """KIS 실시간 종목코드에서 세 자리 거래소 코드를 분리한다.

    Args:
        realtime_symbol: 시세 구분, 거래소, 티커가 결합된 코드.

    Returns:
        세 자리 KIS 해외 거래소 코드.

    Raises:
        ValueError: 거래소 코드를 포함할 만큼 값이 길지 않은 경우.
    """

    if len(realtime_symbol) < 4:
        raise ValueError("Overseas realtime symbol must contain a market code")
    return realtime_symbol[1:4]


def to_trade_row(dto: KISOverseasTrade, received_at: datetime) -> OverseasTrade:
    """해외 체결 DTO를 저장 가능한 ORM 행으로 변환한다.

    Args:
        dto: KIS 해외주식 실시간 체결 DTO.
        received_at: 애플리케이션이 DTO를 꺼낸 timezone-aware 시각.

    Returns:
        UTC 시각과 JSON 직렬화 가능한 상세 필드가 채워진 ORM 행.
    """

    return OverseasTrade(
        realtime_symbol=dto.realtime_symbol,
        symbol=dto.symbol,
        market=_market_from_realtime_symbol(dto.realtime_symbol),
        event_ts=kst_datetime(dto.korea_date, dto.korea_time),
        local_business_date=dto.local_business_date,
        decimal_places=dto.decimal_places,
        price=dto.last_price,
        volume=dto.trade_volume,
        cumulative_volume=dto.total_volume,
        cumulative_amount=dto.total_amount,
        best_bid_price=dto.bid_price,
        best_ask_price=dto.ask_price,
        best_bid_quantity=dto.bid_quantity,
        best_ask_quantity=dto.ask_quantity,
        trade_strength=dto.trade_strength,
        market_type=dto.market_type,
        details=dto.model_dump(mode="json", exclude=OVERSEAS_TRADE_DETAIL_EXCLUDES),
        received_at=received_at,
    )


def to_orderbook_row(
    dto: KISOverseasOrderbook,
    received_at: datetime,
) -> OverseasOrderbook:
    """해외 호가 DTO를 저장 가능한 ORM 행으로 변환한다.

    Args:
        dto: KIS 해외주식 실시간 호가 DTO.
        received_at: 애플리케이션이 DTO를 꺼낸 timezone-aware 시각.

    Returns:
        UTC 시각과 10단계 호가가 채워진 ORM 행.

    Raises:
        ValueError: 호가 단계가 비어 있는 경우.
    """

    if not dto.levels:
        raise ValueError("Overseas orderbook must contain at least one level")

    best_level = dto.levels[0]
    return OverseasOrderbook(
        realtime_symbol=dto.realtime_symbol,
        symbol=dto.symbol,
        market=_market_from_realtime_symbol(dto.realtime_symbol),
        event_ts=kst_datetime(dto.korea_date, dto.korea_time),
        decimal_places=dto.decimal_places,
        best_bid_price=best_level.bid_price,
        best_ask_price=best_level.ask_price,
        best_bid_quantity=best_level.bid_quantity,
        best_ask_quantity=best_level.ask_quantity,
        total_bid_quantity=dto.total_bid_quantity,
        total_ask_quantity=dto.total_ask_quantity,
        levels=[level.model_dump(mode="json") for level in dto.levels],
        details=dto.model_dump(mode="json", exclude=OVERSEAS_ORDERBOOK_DETAIL_EXCLUDES),
        received_at=received_at,
    )


class KISOverseasTickRepository:
    """해외주식 체결과 호가 tick을 독립 트랜잭션으로 저장한다."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """비동기 세션 팩토리를 주입받는다.

        Args:
            session_factory: 작업 단위마다 세션을 만드는 SQLAlchemy 팩토리.
        """

        self._session_factory = session_factory

    async def save(
        self,
        event: KISOverseasTrade | KISOverseasOrderbook,
        received_at: datetime,
    ) -> None:
        """체결 또는 호가 한 건을 새 트랜잭션으로 저장한다.

        Args:
            event: 저장할 해외주식 실시간 DTO.
            received_at: 애플리케이션이 DTO를 꺼낸 timezone-aware 시각.
        """

        if isinstance(event, KISOverseasTrade):
            row = to_trade_row(event, received_at)
        else:
            row = to_orderbook_row(event, received_at)

        async with self._session_factory.begin() as session:
            session.add(row)

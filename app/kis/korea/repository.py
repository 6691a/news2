"""국내주식 실시간 DTO를 ORM 모델로 변환하고 저장한다."""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.kis._time import KST, kst_datetime
from app.kis.korea.models import KoreaOrderbook, KoreaTrade
from app.kis.korea.schemas import KISKoreaOrderbook, KISKoreaTrade


KOREA_TRADE_DETAIL_EXCLUDES = {
    "stock_code",
    "current_price",
    "trade_volume",
    "cumulative_volume",
    "cumulative_trade_amount",
    "trade_strength",
    "best_bid_price",
    "best_ask_price",
    "trade_classification_code",
}
KOREA_ORDERBOOK_DETAIL_EXCLUDES = {
    "stock_code",
    "levels",
    "total_bid_quantity",
    "total_ask_quantity",
}


def to_trade_row(dto: KISKoreaTrade, received_at: datetime) -> KoreaTrade:
    """국내 체결 DTO를 저장 가능한 ORM 행으로 변환한다.

    Args:
        dto: KIS 국내주식 실시간 체결 DTO.
        received_at: 애플리케이션이 DTO를 꺼낸 timezone-aware 시각.

    Returns:
        UTC 시각과 JSON 직렬화 가능한 상세 필드가 채워진 ORM 행.
    """

    return KoreaTrade(
        stock_code=dto.stock_code,
        event_ts=kst_datetime(dto.business_date, dto.trade_time),
        price=dto.current_price,
        volume=dto.trade_volume,
        cumulative_volume=dto.cumulative_volume,
        cumulative_amount=dto.cumulative_trade_amount,
        trade_strength=dto.trade_strength,
        best_bid_price=dto.best_bid_price,
        best_ask_price=dto.best_ask_price,
        trade_classification_code=dto.trade_classification_code,
        details=dto.model_dump(mode="json", exclude=KOREA_TRADE_DETAIL_EXCLUDES),
        received_at=received_at,
    )


def to_orderbook_row(
    dto: KISKoreaOrderbook,
    received_at: datetime,
) -> KoreaOrderbook:
    """국내 호가 DTO를 저장 가능한 ORM 행으로 변환한다.

    호가 DTO에는 영업일자가 없으므로 수신 시각의 한국 날짜를 사용한다.

    Args:
        dto: KIS 국내주식 실시간 호가 DTO.
        received_at: 애플리케이션이 DTO를 꺼낸 timezone-aware 시각.

    Returns:
        UTC 시각과 10단계 호가가 채워진 ORM 행.

    Raises:
        ValueError: 호가 단계가 비어 있는 경우.
    """

    if not dto.levels:
        raise ValueError("Korea orderbook must contain at least one level")

    best_level = dto.levels[0]
    received_date_in_korea = received_at.astimezone(KST).date()
    return KoreaOrderbook(
        stock_code=dto.stock_code,
        event_ts=kst_datetime(received_date_in_korea, dto.business_time),
        best_bid_price=best_level.bid_price,
        best_ask_price=best_level.ask_price,
        total_bid_quantity=dto.total_bid_quantity,
        total_ask_quantity=dto.total_ask_quantity,
        levels=[level.model_dump(mode="json") for level in dto.levels],
        details=dto.model_dump(mode="json", exclude=KOREA_ORDERBOOK_DETAIL_EXCLUDES),
        received_at=received_at,
    )


class KISKoreaTickRepository:
    """국내주식 체결과 호가 tick을 독립 트랜잭션으로 저장한다."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """비동기 세션 팩토리를 주입받는다.

        Args:
            session_factory: 작업 단위마다 세션을 만드는 SQLAlchemy 팩토리.
        """

        self._session_factory = session_factory

    async def save(
        self,
        event: KISKoreaTrade | KISKoreaOrderbook,
        received_at: datetime,
    ) -> None:
        """체결 또는 호가 한 건을 새 트랜잭션으로 저장한다.

        Args:
            event: 저장할 국내주식 실시간 DTO.
            received_at: 애플리케이션이 DTO를 꺼낸 timezone-aware 시각.
        """

        if isinstance(event, KISKoreaTrade):
            row = to_trade_row(event, received_at)
        else:
            row = to_orderbook_row(event, received_at)

        async with self._session_factory.begin() as session:
            session.add(row)

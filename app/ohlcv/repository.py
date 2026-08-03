"""OHLCV 수집 결과를 ORM 행으로 변환하고 저장한다."""

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import TypedDict

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logging import get_logger
from app.instruments.models import Instrument, Market
from app.ohlcv.models import Ohlcv
from app.ohlcv.schemas import DailyBarsResult, Timeframe


logger = get_logger(__name__)


class _OhlcvInsertValues(TypedDict):
    instrument_id: int
    timeframe: Timeframe
    ts: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    snapshot_ts: datetime


class OhlcvRepository:
    """봉 데이터를 중복 없이 저장한다."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """비동기 세션 팩토리를 주입받는다.

        Args:
            session_factory: 작업 단위마다 세션을 만드는 SQLAlchemy 팩토리.
        """

        self._session_factory = session_factory

    async def save_daily(
        self,
        results: Sequence[DailyBarsResult],
        snapshot_ts: datetime,
    ) -> int:
        """확정 일봉을 저장한다.

        같은 거래일을 다시 수집하는 것이 정상 동작이라(정기 수집은 최근 구간을 겹쳐
        조회하고, 백필은 기간이 겹칠 수 있다) 값이 달라졌을 때만 갱신한다. 액면분할·증자로
        수정주가가 소급 변경되면 종가가 함께 바뀌므로 종가 비교로 잡힌다.

        Args:
            results: 종목별 일봉 수집 결과.
            snapshot_ts: 응답을 수신한 timezone-aware UTC 시각.

        Returns:
            새로 넣거나 값이 바뀌어 갱신한 행 수. 전부 같은 값이면 0.
        """

        async with self._session_factory.begin() as session:
            instrument_ids = await self._instrument_ids(session)
            rows = self._to_rows(results, instrument_ids, snapshot_ts)
            if not rows:
                logger.info("ohlcv_daily_saved", fetched=0, saved=0)
                return 0

            # values()에 목록을 넘겨 다중 VALUES 단일 문장으로 만든다. execute의 파라미터
            # 목록으로 넘기면 executemany로 쪼개져 rowcount를 신뢰할 수 없다.
            statement = insert(Ohlcv).values(rows)
            statement = statement.on_conflict_do_update(
                constraint="uq_ohlcv_instrument_timeframe_ts",
                set_={
                    "open": statement.excluded.open,
                    "high": statement.excluded.high,
                    "low": statement.excluded.low,
                    "close": statement.excluded.close,
                    "volume": statement.excluded.volume,
                    "snapshot_ts": statement.excluded.snapshot_ts,
                    "updated_at": func.now(),
                },
                where=Ohlcv.close.is_distinct_from(statement.excluded.close),
            )
            saved = (await session.execute(statement)).rowcount

        logger.info("ohlcv_daily_saved", fetched=len(rows), saved=saved)
        return saved

    async def _instrument_ids(self, session: AsyncSession) -> dict[tuple[str, Market], int]:
        """티커·시장으로 instruments.id를 찾을 조회 표를 만든다.

        추적 종목이 열 개 안팎이라 통째로 읽어 메모리에서 맞춘다.

        Args:
            session: 조회에 사용할 세션.

        Returns:
            (ticker, market) 키의 instruments.id 표.
        """

        result = await session.execute(select(Instrument.ticker, Instrument.market, Instrument.id))
        return {(ticker, market): instrument_id for ticker, market, instrument_id in result.all()}

    def _to_rows(
        self,
        results: Sequence[DailyBarsResult],
        instrument_ids: dict[tuple[str, Market], int],
        snapshot_ts: datetime,
    ) -> list[_OhlcvInsertValues]:
        """수집 결과를 삽입할 행 목록으로 펼친다.

        Args:
            results: 종목별 일봉 수집 결과.
            instrument_ids: (ticker, market) 키의 instruments.id 표.
            snapshot_ts: 응답을 수신한 timezone-aware UTC 시각.

        Returns:
            UNIQUE 키가 겹치지 않는 삽입 행 목록.
        """

        # 같은 문장 안에 UNIQUE 키가 겹치는 행이 있으면 PostgreSQL이 ON CONFLICT DO
        # UPDATE를 거부한다. 나중 값이 최신이므로 뒤에 온 행으로 덮는다.
        rows: dict[tuple[int, datetime], _OhlcvInsertValues] = {}
        for result in results:
            instrument_id = instrument_ids.get((result.ticker, result.market))
            if instrument_id is None:
                logger.warning(
                    "ohlcv_instrument_not_registered",
                    ticker=result.ticker,
                    market=result.market.value,
                    skipped_bars=len(result.bars),
                )
                continue

            for bar in result.bars:
                rows[(instrument_id, bar.event_ts)] = {
                    "instrument_id": instrument_id,
                    "timeframe": Timeframe.ONE_DAY,
                    "ts": bar.event_ts,
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                    "snapshot_ts": snapshot_ts,
                }

        return list(rows.values())

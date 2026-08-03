"""미국 국채 수집 결과를 ORM 행으로 변환하고 저장한다."""

from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import TypedDict

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logging import get_logger
from app.macro.us.treasury.models import UsTreasuryBar, UsTreasuryYieldDaily
from app.macro.us.treasury.schemas import (
    TreasuryFinalObservation,
    TreasuryIntradayResult,
    TreasurySeries,
)


logger = get_logger(__name__)


class _TreasuryBarInsertValues(TypedDict):
    series: TreasurySeries
    event_ts: datetime
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    close: Decimal
    snapshot_ts: datetime


class _TreasuryYieldInsertValues(TypedDict):
    series: TreasurySeries
    observation_date: date
    yield_pct: Decimal
    snapshot_ts: datetime


class UsTreasuryYieldRepository:
    """미국 국채 봉·확정치를 중복 없이 저장한다."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """비동기 세션 팩토리를 주입받는다.

        Args:
            session_factory: 작업 단위마다 세션을 만드는 SQLAlchemy 팩토리.
        """

        self._session_factory = session_factory

    async def save_intraday(
        self,
        result: TreasuryIntradayResult,
        snapshot_ts: datetime,
    ) -> int:
        """장중 1분봉을 저장한다.

        폐장·휴장 폴링은 직전 세션 봉을 다시 받아온다. (series, event_ts) UNIQUE 제약
        위에서 ON CONFLICT DO NOTHING으로 흘려보내므로 중복이 쌓이지 않는다.

        Args:
            result: 한 계열의 장중 수집 결과.
            snapshot_ts: 응답을 수신한 timezone-aware UTC 시각.

        Returns:
            실제로 삽입한 행 수. 전부 중복이거나 봉이 없으면 0.
        """

        if not result.bars:
            logger.info("treasury_intraday_saved", series=result.series.value, fetched=0, saved=0)
            return 0

        rows: list[_TreasuryBarInsertValues] = [
            {
                "series": result.series,
                "event_ts": bar.event_ts,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "snapshot_ts": snapshot_ts,
            }
            for bar in result.bars
        ]
        # values()에 목록을 넘겨 다중 VALUES 단일 문장으로 만든다. execute의 파라미터
        # 목록으로 넘기면 executemany로 쪼개져 rowcount를 신뢰할 수 없다.
        statement = (
            insert(UsTreasuryBar).values(rows).on_conflict_do_nothing(constraint="uq_us_treasury_bars_series_event_ts")
        )

        async with self._session_factory.begin() as session:
            saved = (await session.execute(statement)).rowcount

        logger.info(
            "treasury_intraday_saved",
            series=result.series.value,
            fetched=len(rows),
            saved=saved,
        )
        return saved

    async def save_final(
        self,
        observations: Sequence[TreasuryFinalObservation],
        snapshot_ts: datetime,
    ) -> int:
        """일별 확정 수익률을 저장한다.

        하루치 배치와 구간 백필이 같은 경로를 탄다. 확정치는 사후 정정이 드물고 정정되면
        재수집보다 소급 확인이 먼저라, 이미 있는 날짜는 갱신하지 않고 흘려보낸다.

        Args:
            observations: 저장할 확정 수익률 목록. 비어 있으면 아무것도 하지 않는다.
            snapshot_ts: 응답을 수신한 timezone-aware UTC 시각.

        Returns:
            새로 삽입한 행 수. 전부 이미 저장돼 있으면 0.
        """

        if not observations:
            logger.info("treasury_final_saved", fetched=0, saved=0)
            return 0

        rows: list[_TreasuryYieldInsertValues] = [
            {
                "series": observation.series,
                "observation_date": observation.observation_date,
                "yield_pct": observation.yield_pct,
                "snapshot_ts": snapshot_ts,
            }
            for observation in observations
        ]
        statement = (
            insert(UsTreasuryYieldDaily)
            .values(rows)
            .on_conflict_do_nothing(constraint="uq_us_treasury_yield_daily_series_observation_date")
        )

        async with self._session_factory.begin() as session:
            saved = (await session.execute(statement)).rowcount

        logger.info(
            "treasury_final_saved",
            series=observations[0].series.value,
            fetched=len(rows),
            saved=saved,
            first_date=observations[0].observation_date.isoformat(),
            last_date=observations[-1].observation_date.isoformat(),
        )
        return saved

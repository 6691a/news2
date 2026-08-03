"""미국 국채 10년물 수익률·국채선물 수집 스키마."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Self

import pandas as pd
from pydantic import AwareDatetime, BaseModel, model_validator

from app.core.logging import get_logger
from app.macro.us.treasury.exceptions import TreasuryDataUnavailableError


logger = get_logger(__name__)

# 1분봉의 길이. 봉 시작 시각 + 이 간격이 아직 오지 않았으면 값이 더 변한다.
BAR_INTERVAL = timedelta(minutes=1)

# FRED가 휴장일·미공표 관측값에 쓰는 값.
FRED_MISSING_VALUE = "."


class TreasurySeries(StrEnum):
    """수집 대상 미국 국채 계열.

    값이 DB에 그대로 들어가므로 나중에 바꾸면 마이그레이션이 필요하다.
    """

    US_10Y = "US10Y"  # 10Y 수익률 — 값 단위는 %
    ZN_FUTURE = "ZN"  # 10Y T-Note 선물 — 값 단위는 가격 포인트(1/64 분수), 방향성 신호 전용

    @property
    def yahoo_symbol(self) -> str:
        """Yahoo Finance v8 chart API에서 쓰는 심볼."""

        return {
            self.US_10Y: "^TNX",
            self.ZN_FUTURE: "ZN=F",
        }[self]

    @property
    def fred_series_id(self) -> str:
        """FRED 확정치 시리즈 ID.

        Returns:
            FRED series_id 문자열.

        Raises:
            ValueError: 확정치 소스가 없는 계열인 경우.
        """

        if self is TreasurySeries.ZN_FUTURE:
            raise ValueError("ZN 선물에는 FRED 확정치 시리즈가 없습니다.")
        return "DGS10"


class TreasuryPhase(StrEnum):
    """미국 국채 수집 시점."""

    INTRADAY = "intraday"
    FINAL = "final"
    BACKFILL = "backfill"


class TreasuryProbeOptions(BaseModel):
    """미국 국채 수집 실행 옵션."""

    phase: TreasuryPhase
    series: TreasurySeries = TreasurySeries.US_10Y
    target_date: date | None = None  # FINAL은 대상 영업일, BACKFILL은 구간 종료일
    start_date: date | None = None  # BACKFILL 구간 시작일

    @model_validator(mode="after")
    def validate_target_date(self) -> Self:
        """수집 시점과 계열의 조합을 검증한다.

        Returns:
            검증을 통과한 옵션.

        Raises:
            ValueError: 확정 수집에 대상 날짜가 없거나 확정치 소스가 없는 계열이거나,
                장중 수집에 날짜를 주었거나, 백필 구간이 뒤집힌 경우.
        """

        if self.phase is TreasuryPhase.INTRADAY:
            if self.target_date is not None or self.start_date is not None:
                raise ValueError("intraday phase does not accept dates")
            return self

        if self.series is not TreasurySeries.US_10Y:
            raise ValueError("final phase supports US10Y only")
        if self.target_date is None:
            raise ValueError("final phase requires target_date")
        if self.phase is TreasuryPhase.FINAL:
            if self.start_date is not None:
                raise ValueError("final phase does not accept start_date")
        elif self.start_date is None:
            raise ValueError("backfill phase requires start_date")
        elif self.start_date > self.target_date:
            raise ValueError("start_date must not be after target_date")
        return self


# --- 외부 응답 봉투 DTO -----------------------------------------------------


class FredObservationsRequest(BaseModel):
    """FRED observations 요청 query parameter."""

    series_id: str
    api_key: str
    file_type: str = "json"
    observation_start: date
    observation_end: date


class FredObservation(BaseModel):
    """FRED observations 응답의 관측값 한 건."""

    realtime_start: date
    realtime_end: date
    date: date
    value: str  # 수익률 % 문자열. 휴장·미공표면 "."


class FredObservationsEnvelope(BaseModel):
    """FRED series/observations 응답 봉투."""

    realtime_start: date
    realtime_end: date
    observation_start: date
    observation_end: date
    units: str
    output_type: int
    file_type: str
    order_by: str
    sort_order: str
    count: int
    offset: int
    limit: int
    observations: tuple[FredObservation, ...] = ()


# --- 내부 전달 DTO ----------------------------------------------------------


class IntradayBar(BaseModel):
    """장중 1분봉 한 개."""

    event_ts: AwareDatetime  # 봉 시작 시각, UTC
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    # 값 단위는 series에 따름 — US_10Y: 수익률 %(예: 4.641),
    # ZN_FUTURE: 가격 포인트(예: 112.515625).
    close: Decimal


class TreasuryIntradayResult(BaseModel):
    """한 계열의 장중 1분봉 수집 결과."""

    series: TreasurySeries
    bars: tuple[IntradayBar, ...]


class TreasuryFinalObservation(BaseModel):
    """한 계열의 일별 확정 수익률."""

    series: TreasurySeries
    observation_date: date  # ET 영업일
    yield_pct: Decimal  # %, 예: 4.64


def _decimal_or_none(value: object) -> Decimal | None:
    """yfinance 스칼라를 손실 없는 Decimal 또는 None으로 바꾼다.

    Args:
        value: DataFrame의 OHLC 값.

    Returns:
        결측값이면 None, 아니면 문자열 표현을 거친 Decimal.
    """

    if pd.isna(value):
        return None
    return Decimal(str(value))


def parse_history_frame(
    series: TreasurySeries,
    frame: pd.DataFrame,
    as_of: datetime,
) -> TreasuryIntradayResult:
    """yfinance history DataFrame을 장중 1분봉 결과로 변환한다.

    Args:
        series: 조회한 계열.
        frame: timezone-aware 인덱스와 OHLC 열을 가진 DataFrame.
        as_of: 파싱 기준 시각(timezone-aware). 아직 끝나지 않은 봉을 걸러낼 때 쓴다.

    Returns:
        완료된 봉만 담은 수집 결과. 버린 행이 있으면 건수를 로그로 남긴다.

    Raises:
        ValueError: OHLC 열이 빠졌거나 인덱스가 timezone-aware가 아닌 경우.
    """

    missing_columns = {"Open", "High", "Low", "Close"} - set(frame.columns)
    if missing_columns:
        raise ValueError(f"yfinance history columns missing: {sorted(missing_columns)}")
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
        raise ValueError("yfinance history index must be timezone-aware")

    bars: list[IntradayBar] = []
    missing_close = 0
    unsettled = 0
    for event_ts, row in frame.iterrows():
        close = _decimal_or_none(row["Close"])
        if close is None:
            # 거래가 없던 분은 yfinance가 NaN 행으로 돌려줄 수 있다.
            missing_close += 1
            continue

        utc_event_ts = event_ts.to_pydatetime().astimezone(UTC)
        if utc_event_ts + BAR_INTERVAL > as_of:
            # 진행 중인 봉은 값이 아직 변한다. 저장하면 다음 회차가 갱신하지 못한다.
            unsettled += 1
            continue

        bars.append(
            IntradayBar(
                event_ts=utc_event_ts,
                open=_decimal_or_none(row["Open"]),
                high=_decimal_or_none(row["High"]),
                low=_decimal_or_none(row["Low"]),
                close=close,
            )
        )

    if missing_close:
        logger.warning(
            "treasury_intraday_rows_without_close",
            series=series.value,
            received=len(frame.index),
            dropped=missing_close,
        )
    # 응답 형식이 바뀌어 멀쩡한 봉을 버리기 시작해도 이 건수만 보면 드러난다.
    logger.info(
        "treasury_intraday_parsed",
        series=series.value,
        received=len(frame.index),
        parsed=len(bars),
        skipped_unsettled=unsettled,
    )
    return TreasuryIntradayResult(series=series, bars=tuple(bars))


def parse_fred_response(
    series: TreasurySeries,
    target_date: date,
    response: FredObservationsEnvelope,
) -> TreasuryFinalObservation:
    """FRED observations 응답에서 대상 날짜의 확정 수익률을 뽑는다.

    Args:
        series: 조회한 계열.
        target_date: 확정치를 원하는 ET 영업일.
        response: 검증된 FRED observations 응답.

    Returns:
        대상 날짜의 확정 수익률.

    Raises:
        TreasuryDataUnavailableError: 대상 날짜 관측값이 없거나 아직 공표되지 않은 경우.
    """

    for observation in response.observations:
        if observation.date != target_date:
            continue
        if observation.value == FRED_MISSING_VALUE:
            # 휴장일과 미공표는 응답만으로 구분되지 않는다. 재시도로 갈린다.
            break
        return TreasuryFinalObservation(
            series=series,
            observation_date=target_date,
            yield_pct=Decimal(observation.value),
        )

    raise TreasuryDataUnavailableError(f"{target_date.isoformat()} FRED 관측값이 아직 없습니다.")


def parse_fred_observations(
    series: TreasurySeries,
    response: FredObservationsEnvelope,
) -> tuple[TreasuryFinalObservation, ...]:
    """FRED observations 응답에서 값이 있는 관측값을 전부 뽑는다.

    백필용이라 단일일 조회와 달리 결측을 예외로 올리지 않는다. 구간에는 휴장일이 반드시
    섞여 있고, 기준 시작일(`BACKFILL_START`)보다 시리즈가 늦게 시작하는 경우도 결측으로
    온다 — 둘 다 "있는 것만 담는다"가 맞는 처리다.

    Args:
        series: 조회한 계열.
        response: 검증된 FRED observations 응답.

    Returns:
        날짜 오름차순의 확정 수익률 목록. 전부 결측이면 빈 튜플.
        건너뛴 결측이 있으면 건수를 로그로 남긴다.
    """

    observations = tuple(
        TreasuryFinalObservation(
            series=series,
            observation_date=observation.date,
            yield_pct=Decimal(observation.value),
        )
        for observation in sorted(response.observations, key=lambda item: item.date)
        if observation.value != FRED_MISSING_VALUE
    )

    dropped = len(response.observations) - len(observations)
    if dropped:
        # 휴장일과 시리즈 시작 이전은 정상적인 결측이다. 그래도 건수를 남겨야
        # "구간 전체가 결측"인 사고와 구분된다. 백필은 한 번 돌고 끝이라 더 그렇다.
        logger.warning(
            "fred_observations_missing_dropped",
            series=series.value,
            received=len(response.observations),
            dropped=dropped,
        )
    logger.info(
        "fred_observations_parsed",
        series=series.value,
        received=len(response.observations),
        parsed=len(observations),
        first_date=observations[0].observation_date.isoformat() if observations else "",
        last_date=observations[-1].observation_date.isoformat() if observations else "",
    )
    return observations

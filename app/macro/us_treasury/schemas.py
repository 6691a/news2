"""미국 국채 10년물 수익률·국채선물 수집 스키마."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Self

import pandas as pd
from pydantic import AwareDatetime, BaseModel, model_validator

from app.macro.us_treasury.exceptions import TreasuryDataUnavailableError


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


class TreasuryProbeOptions(BaseModel):
    """미국 국채 수집 실행 옵션."""

    phase: TreasuryPhase
    series: TreasurySeries = TreasurySeries.US_10Y
    target_date: date | None = None

    @model_validator(mode="after")
    def validate_target_date(self) -> Self:
        """수집 시점과 계열의 조합을 검증한다.

        Returns:
            검증을 통과한 옵션.

        Raises:
            ValueError: 확정 수집에 대상 날짜가 없거나 확정치 소스가 없는 계열이거나,
                장중 수집에 대상 날짜를 준 경우.
        """

        if self.phase is TreasuryPhase.FINAL:
            if self.target_date is None:
                raise ValueError("final phase requires target_date")
            if self.series is not TreasurySeries.US_10Y:
                raise ValueError("final phase supports US10Y only")
        elif self.target_date is not None:
            raise ValueError("intraday phase does not accept target_date")
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
        완료된 봉만 담은 수집 결과.

    Raises:
        ValueError: OHLC 열이 빠졌거나 인덱스가 timezone-aware가 아닌 경우.
    """

    missing_columns = {"Open", "High", "Low", "Close"} - set(frame.columns)
    if missing_columns:
        raise ValueError(f"yfinance history columns missing: {sorted(missing_columns)}")
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
        raise ValueError("yfinance history index must be timezone-aware")

    bars: list[IntradayBar] = []
    for event_ts, row in frame.iterrows():
        close = _decimal_or_none(row["Close"])
        if close is None:
            # 거래가 없던 분은 yfinance가 NaN 행으로 돌려줄 수 있다.
            continue

        utc_event_ts = event_ts.to_pydatetime().astimezone(UTC)
        if utc_event_ts + BAR_INTERVAL > as_of:
            # 진행 중인 봉은 값이 아직 변한다. 저장하면 다음 회차가 갱신하지 못한다.
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

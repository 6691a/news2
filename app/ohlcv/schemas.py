"""OHLCV 수집 스키마.

일봉(확정값)과 분봉(장중)이 같은 테이블·같은 DTO를 쓰고 `Timeframe`으로만 갈린다.
P0에서 구현하는 것은 일봉이며, 분봉은 같은 자리에 붙는다.
"""

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Self
from zoneinfo import ZoneInfo

import pandas as pd
from pydantic import AwareDatetime, BaseModel, Field, field_validator, model_validator

from app.core._time import ET, HKT, JST, KST, SHANGHAI, TAIPEI
from app.core.logging import get_logger
from app.instruments.models import Market
from app.kis.schemas.common import KISBaseModel


logger = get_logger(__name__)


class Timeframe(StrEnum):
    """저장하는 봉의 간격.

    값이 DB에 그대로 들어가므로 나중에 바꾸면 마이그레이션이 필요하다. 분봉은 P1이
    사용하지만 CHECK 제약을 두 번 고치지 않으려고 처음부터 넣는다.
    """

    ONE_MINUTE = "1m"
    ONE_DAY = "1d"


class OhlcvScope(StrEnum):
    """한 번의 수집이 다룰 시장 범위.

    소스와 마감 시각이 달라 국내와 해외를 같은 스케줄로 묶을 수 없다.
    """

    KOREA = "korea"
    OVERSEAS = "overseas"
    ALL = "all"

    @property
    def markets(self) -> frozenset[Market]:
        """범위에 속한 거래 시장 집합.

        해외는 시장을 나열하지 않고 "국내가 아닌 전부"로 잡는다. 매크로 시장(지수·환율·
        선물)을 늘릴 때마다 이 목록을 같이 고치는 걸 잊으면 그 계열만 조용히 빠진다.
        """

        korea = frozenset({Market.KRX})
        overseas = frozenset(Market) - korea
        return {
            OhlcvScope.KOREA: korea,
            OhlcvScope.OVERSEAS: overseas,
            OhlcvScope.ALL: frozenset(Market),
        }[self]


# 시장별 (현지 시간대, 현지 자정부터 마감까지의 시간).
#
# 마감 시각에 여유 10분을 더해, 마감 동시호가로 종가가 확정되는 시간과 소스 반영 지연을
# 함께 흡수한다. 이 시각이 지나야 그 날의 일봉을 확정값으로 본다. 조기 폐장일(미국 반휴장,
# 국내 수능일 등)은 실제 마감이 이보다 이르므로 문제되지 않는다.
#
# 24시간 시장(FX)은 마감이 없어 하루가 끝나야 확정으로 본다 — 그래서 오프셋이 24시간이다.
# 시각(time)이 아니라 간격(timedelta)으로 둔 이유가 이것이다.
MARKET_SESSION: dict[Market, tuple[ZoneInfo, timedelta]] = {
    Market.KRX: (KST, timedelta(hours=15, minutes=40)),  # 정규장 15:30
    Market.NASDAQ: (ET, timedelta(hours=16, minutes=10)),  # 16:00
    Market.NYSE: (ET, timedelta(hours=16, minutes=10)),
    Market.NYSE_ARCA: (ET, timedelta(hours=16, minutes=10)),
    Market.US_INDEX: (ET, timedelta(hours=16, minutes=10)),
    Market.JPX: (JST, timedelta(hours=15, minutes=10)),  # 15:00
    Market.HKEX: (HKT, timedelta(hours=16, minutes=10)),  # 16:00
    Market.SSE: (SHANGHAI, timedelta(hours=15, minutes=10)),  # 15:00
    Market.TWSE: (TAIPEI, timedelta(hours=13, minutes=40)),  # 13:30
    Market.GLOBEX: (ET, timedelta(hours=17, minutes=10)),  # 일일 세션 17:00 종료
    Market.FX: (ET, timedelta(days=1)),  # 마감 없음. 날이 바뀌어야 확정
}

# 기간을 지정하지 않은 정기 수집이 되돌아볼 구간. 휴장과 재시도로 한 회차를 놓쳐도
# 다음 회차가 메운다. 저장이 멱등이라 겹쳐도 무해하다.
DEFAULT_LOOKBACK = timedelta(days=7)

# KIS 국내주식기간별시세는 한 번에 최대 100건을 준다. 백필은 이 크기로 쪼갠다.
# 달력일 기준이라 100 영업일보다 짧게 잡아야 응답이 잘리지 않는다.
KOREA_CHART_MAX_ROWS = 100

KOREA_DAILY_CHART_TR_ID = "FHKST03010100"
KOREA_DAILY_CHART_PATH = "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"

# KIS 업무 정상 응답 코드.
KIS_SUCCESS_CODE = "0"


def market_zone(market: Market) -> ZoneInfo:
    """거래 시장의 현지 시간대를 반환한다.

    Args:
        market: 대상 거래 시장.

    Returns:
        거래소 현지 시간대.
    """

    zone, _ = MARKET_SESSION[market]
    return zone


def session_start(market: Market, session_date: date) -> datetime:
    """거래일 현지 00:00을 봉 시작 UTC 시각으로 바꾼다.

    일봉과 분봉이 `ts` 컬럼 하나를 공유하므로 일봉도 timestamp로 저장한다. 현지
    거래일로 되돌릴 때는 거래소 시간대로 변환한다.

    Args:
        market: 대상 거래 시장.
        session_date: 거래소 현지 거래일.

    Returns:
        봉 시작 시각의 UTC 값.
    """

    return datetime.combine(session_date, time.min, tzinfo=market_zone(market)).astimezone(UTC)


def session_settled(market: Market, bar_start: datetime, as_of: datetime) -> bool:
    """해당 봉이 확정된 뒤인지 판단한다.

    장중에 조회하면 소스가 진행 중인 당일 봉을 함께 준다. 그대로 저장하면 미완성
    종가가 확정값 자리에 들어가 백테스트가 오염된다.

    Args:
        market: 대상 거래 시장.
        bar_start: 봉 시작 시각(거래소 현지 자정에 해당하는 timezone-aware 값).
        as_of: 판단 기준 시각(timezone-aware).

    Returns:
        마감 시각이 지났으면 True.
    """

    _, close_offset = MARKET_SESSION[market]
    return bar_start + close_offset <= as_of


# --- 내부 전달 DTO ----------------------------------------------------------


class DailyBar(BaseModel):
    """확정 일봉 한 개."""

    event_ts: AwareDatetime  # 거래일 현지 00:00에 대응하는 UTC 시각
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int


class DailyBarsResult(BaseModel):
    """종목 하나의 일봉 수집 결과."""

    ticker: str
    market: Market
    bars: tuple[DailyBar, ...]


class OhlcvCollectOptions(BaseModel):
    """OHLCV 수집 실행 옵션."""

    scope: OhlcvScope = OhlcvScope.ALL
    start: date | None = None
    end: date | None = None

    @model_validator(mode="after")
    def validate_period(self) -> Self:
        """조회 기간의 짝과 순서를 검증한다.

        종료일만 주는 것은 시작일을 알 수 없어 거부한다. 시작일만 주는 것은 "그날부터
        오늘까지"라는 뜻이라 허용한다(백필의 기본 형태).

        Returns:
            검증을 통과한 옵션.

        Raises:
            ValueError: 시작일 없이 종료일만 주었거나 순서가 뒤집힌 경우.
        """

        if self.start is None and self.end is not None:
            raise ValueError("end requires start")
        if self.start is not None and self.end is not None and self.start > self.end:
            raise ValueError("start must not be after end")
        return self

    def period(self, market: Market, as_of: datetime) -> tuple[date, date]:
        """대상 시장의 조회 기간을 결정한다.

        종료일은 거래소 현지 날짜를 쓴다. 국내와 미국은 같은 순간에도 날짜가 다를 수 있어
        시장마다 따로 계산한다.

        Args:
            market: 대상 거래 시장.
            as_of: 기준 시각(timezone-aware).

        Returns:
            (시작일, 종료일). 시작일이 없으면 최근 구간, 종료일이 없으면 현지 오늘까지.
        """

        today = as_of.astimezone(market_zone(market)).date()
        if self.start is None:
            return today - DEFAULT_LOOKBACK, today
        return self.start, self.end or today


# --- KIS 국내주식기간별시세 (TR FHKST03010100) -------------------------------


class KoreaChartMarketCode(StrEnum):
    """국내주식 기간별시세 조건 시장 분류 코드."""

    KRX = "J"
    NXT = "NX"
    UNIFIED = "UN"


class KoreaChartPeriodCode(StrEnum):
    """국내주식 기간별시세 기간 분류 코드."""

    DAY = "D"
    WEEK = "W"
    MONTH = "M"
    YEAR = "Y"


class KoreaChartAdjustCode(StrEnum):
    """국내주식 기간별시세 수정주가 반영 여부.

    수정주가는 액면분할·증자만 소급 반영하고 배당은 반영하지 않는다. 배당까지
    반영하는 Yahoo `auto_adjust`(해외)와 기준이 다르므로 국내·해외 수익률을
    같은 축에서 비교할 때 주의한다.
    """

    ADJUSTED = "0"
    ORIGINAL = "1"


class KoreaDailyChartParams(KISBaseModel):
    """국내주식 기간별시세 조회 파라미터."""

    market_code: KoreaChartMarketCode = Field(serialization_alias="FID_COND_MRKT_DIV_CODE")
    stock_code: str = Field(serialization_alias="FID_INPUT_ISCD")
    start_date: str = Field(serialization_alias="FID_INPUT_DATE_1", pattern=r"^\d{8}$")
    end_date: str = Field(serialization_alias="FID_INPUT_DATE_2", pattern=r"^\d{8}$")
    period_code: KoreaChartPeriodCode = Field(serialization_alias="FID_PERIOD_DIV_CODE")
    adjust_code: KoreaChartAdjustCode = Field(serialization_alias="FID_ORG_ADJ_PRC")


class KoreaDailyChartRow(BaseModel):
    """국내주식 기간별시세 output2 원소 하나."""

    stck_bsop_date: str  # 주식 영업일자(YYYYMMDD)
    stck_oprc: Decimal  # 시가(원)
    stck_hgpr: Decimal  # 최고가(원)
    stck_lwpr: Decimal  # 최저가(원)
    stck_clpr: Decimal  # 종가(원)
    acml_vol: int  # 누적 거래량(주)


class KoreaDailyChartBody(BaseModel):
    """TR FHKST03010100 응답 본문.

    output1(종목 기준정보)은 일봉 저장에 쓰지 않아 선언하지 않는다.
    """

    rt_cd: str  # 결과 코드("0": 성공)
    msg_cd: str  # 응답 메시지 코드
    msg1: str  # 응답 메시지
    output2: list[KoreaDailyChartRow] = Field(default_factory=list)

    @field_validator("output2", mode="before")
    @classmethod
    def drop_blank_rows(cls, value: object) -> object:
        """값이 비어 있는 자리 채움 행을 파싱 전에 걸러낸다.

        요청 기간의 거래일 수가 응답 정원보다 적으면 빈 문자열 행이 섞여 올 수 있다.
        같은 계열의 투자자 수급 TR에서는 **영업일자만 채우고 나머지를 전부 빈 문자열로**
        보내는 것이 실제로 확인됐다(NXT 출범 전 구간). 그래서 날짜와 종가를 함께 본다.
        값이 없는 행이라 버려도 잃는 정보가 없지만, 두면 숫자 필드 파싱이 통째로 깨진다.

        버린 게 있으면 반드시 로그로 남긴다 — 응답 형식이 바뀌어 멀쩡한 행을 버리기
        시작해도 건수만 보면 드러난다.

        Args:
            value: 검증 전 output2 값.

        Returns:
            영업일자와 종가가 모두 채워진 행만 남긴 목록. 목록이 아니면 원본 그대로 돌려준다.
        """

        if not isinstance(value, list):
            return value

        rows = [
            row for row in value if not isinstance(row, dict) or (row.get("stck_bsop_date") and row.get("stck_clpr"))
        ]
        if len(rows) != len(value):
            logger.warning(
                "kis_daily_chart_blank_rows_dropped",
                received=len(value),
                dropped=len(value) - len(rows),
            )
        return rows


def parse_korea_daily_chart(
    ticker: str,
    body: KoreaDailyChartBody,
    as_of: datetime,
) -> DailyBarsResult:
    """KIS 기간별시세 응답을 확정 일봉 결과로 변환한다.

    Args:
        ticker: 조회한 종목 코드.
        body: 검증된 응답 본문.
        as_of: 파싱 기준 시각(timezone-aware). 마감 전 거래일을 걸러낼 때 쓴다.

    Returns:
        마감이 끝난 거래일의 일봉만 담은 결과.
    """

    bars: list[DailyBar] = []
    unsettled = 0
    for row in body.output2:
        session_date = datetime.strptime(row.stck_bsop_date, "%Y%m%d").date()
        bar_start = session_start(Market.KRX, session_date)
        if not session_settled(Market.KRX, bar_start, as_of):
            unsettled += 1
            continue

        bars.append(
            DailyBar(
                event_ts=bar_start,
                open=row.stck_oprc,
                high=row.stck_hgpr,
                low=row.stck_lwpr,
                close=row.stck_clpr,
                volume=row.acml_vol,
            )
        )

    # KIS는 최신 거래일부터 내려주므로 저장·로그가 읽기 쉽도록 오름차순으로 되돌린다.
    bars.sort(key=lambda bar: bar.event_ts)
    logger.info(
        "kis_daily_chart_parsed",
        ticker=ticker,
        received=len(body.output2),
        parsed=len(bars),
        skipped_unsettled=unsettled,
    )
    return DailyBarsResult(ticker=ticker, market=Market.KRX, bars=tuple(bars))


# --- Yahoo 해외주식 일봉 ----------------------------------------------------


def _decimal_or_none(value: object) -> Decimal | None:
    """yfinance 스칼라를 손실 없는 Decimal 또는 None으로 바꾼다.

    Args:
        value: DataFrame의 OHLCV 값.

    Returns:
        결측값이면 None, 아니면 문자열 표현을 거친 Decimal.
    """

    if pd.isna(value):
        return None
    return Decimal(str(value))


def parse_yahoo_daily_frame(
    ticker: str,
    market: Market,
    frame: pd.DataFrame,
    as_of: datetime,
) -> DailyBarsResult:
    """yfinance history DataFrame을 확정 일봉 결과로 변환한다.

    Args:
        ticker: 조회한 종목 티커.
        market: 종목이 상장된 거래 시장.
        frame: timezone-aware 인덱스와 OHLCV 열을 가진 DataFrame.
        as_of: 파싱 기준 시각(timezone-aware). 마감 전 거래일을 걸러낼 때 쓴다.

    Returns:
        마감이 끝난 거래일의 일봉만 담은 결과.

    Raises:
        ValueError: OHLCV 열이 빠졌거나 인덱스가 timezone-aware가 아닌 경우.
    """

    missing_columns = {"Open", "High", "Low", "Close", "Volume"} - set(frame.columns)
    if missing_columns:
        raise ValueError(f"yfinance history columns missing: {sorted(missing_columns)}")
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
        raise ValueError("yfinance history index must be timezone-aware")

    bars: list[DailyBar] = []
    missing_price = 0
    unsettled = 0
    for index_ts, row in frame.iterrows():
        values = [_decimal_or_none(row[column]) for column in ("Open", "High", "Low", "Close")]
        if any(value is None for value in values):
            # 거래가 없던 날은 yfinance가 NaN 행으로 돌려줄 수 있다.
            missing_price += 1
            continue

        # 일봉 인덱스는 이미 거래소 현지 자정이다. 우리가 시간대를 다시 계산하지 않고
        # 소스가 준 값을 그대로 UTC로 옮긴다 — 시장별 시간대 표를 틀려도 날짜가 밀리지 않는다.
        bar_start = index_ts.to_pydatetime().astimezone(UTC)
        if not session_settled(market, bar_start, as_of):
            unsettled += 1
            continue

        open_price, high, low, close = values
        assert open_price is not None and high is not None and low is not None and close is not None
        # 지수·환율은 체결이 없어 거래량이 NaN이나 0으로 온다. 가격이 멀쩡한 봉을 거래량
        # 때문에 버리면 그 계열이 통째로 사라진다.
        volume = _decimal_or_none(row["Volume"])
        bars.append(
            DailyBar(
                event_ts=bar_start,
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=int(volume) if volume is not None else 0,
            )
        )

    if missing_price:
        logger.warning(
            "yahoo_daily_chart_rows_without_price",
            ticker=ticker,
            received=len(frame.index),
            dropped=missing_price,
        )
    logger.info(
        "yahoo_daily_chart_parsed",
        ticker=ticker,
        received=len(frame.index),
        parsed=len(bars),
        skipped_unsettled=unsettled,
    )
    return DailyBarsResult(ticker=ticker, market=market, bars=tuple(bars))

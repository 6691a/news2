"""미국 국채 수익률·국채선물 수집 서비스."""

import asyncio
from datetime import date

import httpx
import yfinance as yf
from yfinance.exceptions import YFRateLimitError

from app.core.config import Settings
from app.core.http import raise_for_status
from app.core.logging import get_logger
from app.core.models import utc_now
from app.macro.us_treasury.exceptions import TreasuryDataUnavailableError, YahooRetryableError
from app.macro.us_treasury.schemas import (
    FredObservationsEnvelope,
    FredObservationsRequest,
    TreasuryFinalObservation,
    TreasuryIntradayResult,
    TreasurySeries,
    parse_fred_response,
    parse_history_frame,
)


logger = get_logger(__name__)

FRED_OBSERVATIONS_URL = "https://api.stlouisfed.org/fred/series/observations"


class UsTreasuryYieldService:
    """Yahoo 장중 1분봉과 FRED 일별 확정치를 수집한다."""

    def __init__(self, settings: Settings) -> None:
        """수집 서비스 의존성을 초기화한다.

        Args:
            settings: FRED API 키를 담은 설정.
        """

        self.settings = settings

    async def collect_intraday(
        self,
        series: TreasurySeries,
    ) -> TreasuryIntradayResult:
        """yfinance에서 계열의 장중 1분봉을 수집한다.

        Args:
            series: 수집할 계열. 수익률(^TNX)과 국채선물(ZN=F)이 같은 경로를 탄다.

        Returns:
            완료된 봉만 담은 수집 결과.

        Raises:
            YFRateLimitError: Yahoo 쿼터(429)에 막힌 경우. 재시도하지 않는다.
            YahooRetryableError: 그 밖의 yfinance 호출이 실패한 경우.
            TreasuryDataUnavailableError: 응답에 봉이 없는 경우.
        """

        try:
            frame = await asyncio.to_thread(
                yf.Ticker(series.yahoo_symbol).history,
                period="1d",
                interval="1m",
                prepost=False,
                auto_adjust=False,
                actions=False,
                repair=False,
                keepna=False,
                raise_errors=True,
            )
        except YFRateLimitError:
            raise
        except Exception as error:
            raise YahooRetryableError(f"{series.yahoo_symbol} yfinance 호출에 실패했습니다.") from error

        if frame.empty:
            raise TreasuryDataUnavailableError(f"{series.yahoo_symbol} history 응답에 봉이 없습니다.")
        return parse_history_frame(series, frame, as_of=utc_now())

    async def collect_final(
        self,
        series: TreasurySeries,
        target_date: date,
        client: httpx.AsyncClient,
    ) -> TreasuryFinalObservation:
        """FRED H.15 시리즈에서 대상 영업일의 확정 수익률을 수집한다.

        Args:
            series: 수집할 계열. 확정치 소스가 있는 계열이어야 한다.
            target_date: 확정치를 원하는 ET 영업일.
            client: 요청에 사용할 비동기 HTTP 클라이언트.

        Returns:
            대상 날짜의 확정 수익률.

        Raises:
            ValueError: FRED API 키가 설정되지 않은 경우.
            httpx.HTTPError: 네트워크 전송에 실패하거나 응답이 4xx·5xx인 경우.
            TreasuryDataUnavailableError: 대상 날짜 관측값이 아직 없는 경우.
        """

        if not self.settings.fred_api_key:
            raise ValueError("FRED_API_KEY 설정이 필요합니다.")

        request = FredObservationsRequest(
            series_id=series.fred_series_id,
            api_key=self.settings.fred_api_key,
            observation_start=target_date,
            observation_end=target_date,
        )
        response = await client.get(
            url=FRED_OBSERVATIONS_URL,
            headers={"Accept": "application/json"},
            params=request.model_dump(mode="json"),
        )
        raise_for_status(
            response,
            source="fred_observations",
            series=series.value,
            target_date=target_date.isoformat(),
        )

        fred_response = FredObservationsEnvelope.model_validate(response.json())
        return parse_fred_response(series, target_date, fred_response)

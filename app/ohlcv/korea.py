"""KIS 국내주식 확정 일봉 수집 서비스."""

import asyncio
from datetime import date, timedelta
from typing import Protocol

import httpx

from app.core.collection import KIS_REQUEST_INTERVAL_SECONDS
from app.core.config import Settings
from app.core.http import raise_for_status
from app.core.logging import get_logger
from app.core.models import utc_now
from app.instruments.models import Market
from app.kis.schemas import KISAuthTokenResponse
from app.kis.schemas.common import KISQueryHeaders
from app.ohlcv.exceptions import OhlcvSourceError
from app.ohlcv.schemas import (
    DailyBar,
    DailyBarsResult,
    KIS_SUCCESS_CODE,
    KOREA_CHART_MAX_ROWS,
    KOREA_DAILY_CHART_PATH,
    KOREA_DAILY_CHART_TR_ID,
    KoreaChartAdjustCode,
    KoreaChartMarketCode,
    KoreaChartPeriodCode,
    KoreaDailyChartBody,
    KoreaDailyChartParams,
    parse_korea_daily_chart,
)


logger = get_logger(__name__)


class _KISRestTokenProvider(Protocol):
    async def get_auth_token(self) -> KISAuthTokenResponse: ...


def split_period(start: date, end: date) -> list[tuple[date, date]]:
    """조회 기간을 KIS 응답 정원에 맞는 구간으로 쪼갠다.

    한 번에 최대 100건이라 긴 백필은 나눠 호출해야 한다. 달력일로 자르므로 한 구간의
    거래일 수는 정원보다 항상 적다.

    Args:
        start: 조회 시작일.
        end: 조회 종료일.

    Returns:
        오래된 구간부터 정렬된 (시작일, 종료일) 목록.
    """

    chunk = timedelta(days=KOREA_CHART_MAX_ROWS - 1)
    periods: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        chunk_end = min(cursor + chunk, end)
        periods.append((cursor, chunk_end))
        cursor = chunk_end + timedelta(days=1)
    return periods


class KISKoreaDailyChartService:
    """KIS 국내주식기간별시세(TR FHKST03010100)로 확정 일봉을 수집한다."""

    def __init__(self, settings: Settings, auth: _KISRestTokenProvider) -> None:
        """수집 서비스 의존성을 초기화한다.

        Args:
            settings: 실전 KIS 도메인과 인증 설정.
            auth: REST 접근 토큰 제공자.
        """

        self.settings = settings
        self.auth = auth

    async def collect_daily(
        self,
        ticker: str,
        start: date,
        end: date,
        client: httpx.AsyncClient,
    ) -> DailyBarsResult:
        """한 종목의 확정 일봉을 기간만큼 수집한다.

        Args:
            ticker: 국내 종목 코드.
            start: 조회 시작일(한국 날짜).
            end: 조회 종료일(한국 날짜).
            client: 요청에 사용할 비동기 HTTP 클라이언트.

        Returns:
            마감이 끝난 거래일의 일봉만 담은 결과.

        Raises:
            ValueError: 모의투자 설정으로 실행한 경우.
            httpx.HTTPError: 네트워크 전송에 실패하거나 응답이 4xx·5xx인 경우.
            OhlcvSourceError: KIS가 업무 오류(rt_cd != "0")를 돌려준 경우.
        """

        if self.settings.kis_virtual:
            raise ValueError("실전키 수집은 KIS_VIRTUAL=false 설정이 필요합니다.")

        token = await self.auth.get_auth_token()
        headers = KISQueryHeaders(
            authorization=f"Bearer {token.access_token}",
            app_key=self.settings.kis_app_key,
            app_secret=self.settings.kis_app_secret,
            tr_id=KOREA_DAILY_CHART_TR_ID,
        ).model_dump(mode="json")

        bars: list[DailyBar] = []
        for chunk_start, chunk_end in split_period(start, end):
            await asyncio.sleep(KIS_REQUEST_INTERVAL_SECONDS)
            params = KoreaDailyChartParams(
                market_code=KoreaChartMarketCode.KRX,
                stock_code=ticker,
                start_date=chunk_start.strftime("%Y%m%d"),
                end_date=chunk_end.strftime("%Y%m%d"),
                period_code=KoreaChartPeriodCode.DAY,
                adjust_code=KoreaChartAdjustCode.ADJUSTED,
            )
            response = await client.get(
                url=f"{self.settings.kis_rest_domain.rstrip('/')}{KOREA_DAILY_CHART_PATH}",
                headers=headers,
                params=params.model_dump(mode="json"),
            )
            # 5xx는 KIS나 게이트웨이의 일시 장애다. 예외로 올려야 Celery가 재시도한다.
            raise_for_status(
                response,
                source="kis_korea_daily_chart",
                tr_id=KOREA_DAILY_CHART_TR_ID,
                ticker=ticker,
            )

            body = KoreaDailyChartBody.model_validate(response.json())
            if body.rt_cd != KIS_SUCCESS_CODE:
                logger.error(
                    "kis_daily_chart_business_error",
                    ticker=ticker,
                    rt_cd=body.rt_cd,
                    msg_cd=body.msg_cd,
                    msg1=body.msg1,
                    start=chunk_start.isoformat(),
                    end=chunk_end.isoformat(),
                )
                raise OhlcvSourceError(f"{ticker} 일봉 조회가 실패했습니다: {body.msg_cd}")

            chunk_result = parse_korea_daily_chart(ticker, body, as_of=utc_now())
            bars.extend(chunk_result.bars)

        return DailyBarsResult(ticker=ticker, market=Market.KRX, bars=tuple(bars))

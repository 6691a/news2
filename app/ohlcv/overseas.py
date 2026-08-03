"""Yahoo 해외주식 확정 일봉 수집 서비스."""

import asyncio
from datetime import date, timedelta

import yfinance as yf
from yfinance.exceptions import YFRateLimitError

from app.core.logging import get_logger
from app.core.models import utc_now
from app.instruments.models import Market
from app.ohlcv.exceptions import YahooRetryableError
from app.ohlcv.schemas import DailyBarsResult, parse_yahoo_daily_frame


logger = get_logger(__name__)


class YahooDailyChartService:
    """yfinance로 해외주식 확정 일봉을 수집한다.

    `auto_adjust=True`라 배당·분할이 모두 소급 반영된 총수익 기준 가격이 온다.
    액면분할만 반영하는 국내 KIS 수정주가와 조정 기준이 다르다.
    """

    async def collect_daily(
        self,
        ticker: str,
        market: Market,
        start: date,
        end: date,
        symbol: str | None = None,
    ) -> DailyBarsResult:
        """한 종목·지수의 확정 일봉을 기간만큼 수집한다.

        Args:
            ticker: 저장 키가 될 종목 티커(`instruments.ticker`).
            market: 종목이 상장된 거래 시장.
            start: 조회 시작일(거래소 현지 날짜).
            end: 조회 종료일(거래소 현지 날짜, 포함).
            symbol: yfinance에 넘길 심볼. 티커와 다를 때만 준다(예: KOSPI → `^KS11`).

        Returns:
            마감이 끝난 거래일의 일봉만 담은 결과. 기간에 거래일이 없으면 빈 결과.

        Raises:
            YFRateLimitError: Yahoo 쿼터(429)에 막힌 경우. 재시도하지 않는다.
            YahooRetryableError: 그 밖의 yfinance 호출이 실패한 경우.
        """

        request_symbol = symbol or ticker
        try:
            frame = await asyncio.to_thread(
                yf.Ticker(request_symbol).history,
                start=start,
                # yfinance의 end는 미포함이라 하루를 더해야 종료일이 들어온다.
                end=end + timedelta(days=1),
                interval="1d",
                prepost=False,
                auto_adjust=True,
                actions=False,
                repair=False,
                keepna=False,
                raise_errors=True,
            )
        except YFRateLimitError:
            raise
        except Exception as error:
            raise YahooRetryableError(f"{request_symbol} yfinance 호출에 실패했습니다.") from error

        if frame.empty:
            # 휴장 구간만 조회하면 정상적으로 빈 응답이 온다. 없는 심볼도 빈 프레임으로
            # 오므로(yfinance가 예외를 올리지 않는다) 경고로 남겨 오타를 드러낸다.
            logger.warning(
                "yahoo_daily_chart_empty",
                ticker=ticker,
                symbol=request_symbol,
                start=start.isoformat(),
                end=end.isoformat(),
            )
            return DailyBarsResult(ticker=ticker, market=market, bars=())

        return parse_yahoo_daily_frame(ticker, market, frame, as_of=utc_now())

from datetime import date

import pandas as pd
import pytest
from structlog.testing import capture_logs
from yfinance.exceptions import YFRateLimitError

from app.instruments.models import Market
from app.ohlcv import overseas as overseas_module
from app.ohlcv.exceptions import YahooRetryableError
from app.ohlcv.overseas import YahooDailyChartService
from tests.ohlcv.fixtures import yahoo_daily_frame


START = date(2026, 7, 24)
END = date(2026, 7, 31)

# yfinance history에 넘기는 고정 옵션. end는 미포함이라 종료일 다음 날을 넘겨야 한다.
HISTORY_OPTIONS: dict[str, object] = {
    "start": START,
    "end": date(2026, 8, 1),
    "interval": "1d",
    "prepost": False,
    # 해외는 배당까지 소급 반영한다. 액면분할만 반영하는 국내 KIS 수정주가와 기준이 다르다.
    "auto_adjust": True,
    "actions": False,
    "repair": False,
    "keepna": False,
    "raise_errors": True,
}


def _patch_ticker(
    monkeypatch: pytest.MonkeyPatch,
    frame: pd.DataFrame | None = None,
    error: Exception | None = None,
) -> list[tuple[str, dict[str, object]]]:
    """yf.Ticker를 가짜로 바꾸고 호출 기록 목록을 돌려준다.

    Args:
        monkeypatch: 교체에 사용할 pytest 픽스처.
        frame: history가 돌려줄 DataFrame.
        error: history가 대신 올릴 예외.

    Returns:
        (요청 심볼, history kwargs) 호출 기록. 테스트가 그대로 검사한다.
    """

    calls: list[tuple[str, dict[str, object]]] = []

    class FakeTicker:
        def __init__(self, ticker: str) -> None:
            self.ticker = ticker

        def history(self, **kwargs: object) -> pd.DataFrame:
            calls.append((self.ticker, kwargs))
            if error is not None:
                raise error
            assert frame is not None
            return frame

    monkeypatch.setattr(overseas_module.yf, "Ticker", FakeTicker)
    return calls


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("ticker", "symbol", "expected_symbol", "market"),
    [
        ("AAPL", None, "AAPL", Market.NASDAQ),
        # 국내 지수는 종목 시세 TR로 못 받아 Yahoo 심볼로 우회한다.
        ("KOSPI", "^KS11", "^KS11", Market.KRX),
    ],
)
async def test_collect_daily_requests_source_symbol_with_inclusive_end(
    monkeypatch: pytest.MonkeyPatch,
    ticker: str,
    symbol: str | None,
    expected_symbol: str,
    market: Market,
) -> None:
    calls = _patch_ticker(monkeypatch, frame=yahoo_daily_frame())

    result = await YahooDailyChartService().collect_daily(ticker, market, START, END, symbol=symbol)

    assert calls == [(expected_symbol, HISTORY_OPTIONS)]
    # 저장 키는 소스 심볼이 아니라 티커다. 뒤바뀌면 종목이 통째로 어긋난다.
    assert (result.ticker, result.market) == (ticker, market)
    assert len(result.bars) == 2


@pytest.mark.asyncio
async def test_collect_daily_warns_and_returns_empty_when_frame_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 없는 심볼도 예외가 아니라 빈 프레임으로 온다. 오타를 드러내는 유일한 신호다.
    _patch_ticker(monkeypatch, frame=yahoo_daily_frame().iloc[:0])

    with capture_logs() as logs:
        result = await YahooDailyChartService().collect_daily("NOPE", Market.NASDAQ, START, END)

    assert result.bars == ()
    assert (result.ticker, result.market) == ("NOPE", Market.NASDAQ)
    empty = [entry for entry in logs if entry["event"] == "yahoo_daily_chart_empty"]
    assert len(empty) == 1
    assert empty[0]["log_level"] == "warning"
    assert (empty[0]["ticker"], empty[0]["symbol"]) == ("NOPE", "NOPE")


@pytest.mark.asyncio
async def test_collect_daily_does_not_wrap_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    # 쿼터 초과를 재시도 대상으로 감싸면 Celery가 다시 물어 쿼터를 더 태운다.
    _patch_ticker(monkeypatch, error=YFRateLimitError())

    with pytest.raises(YFRateLimitError):
        await YahooDailyChartService().collect_daily("AAPL", Market.NASDAQ, START, END)


@pytest.mark.asyncio
async def test_collect_daily_wraps_other_yfinance_errors_for_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_ticker(monkeypatch, error=RuntimeError("upstream unavailable"))

    with pytest.raises(YahooRetryableError, match="AAPL"):
        await YahooDailyChartService().collect_daily("AAPL", Market.NASDAQ, START, END)

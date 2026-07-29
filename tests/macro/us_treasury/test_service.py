from datetime import date
from decimal import Decimal

import httpx
import pandas as pd
import pytest
from fastapi import status
from yfinance.exceptions import YFRateLimitError

from app.macro.us_treasury import service as service_module
from app.macro.us_treasury.exceptions import TreasuryDataUnavailableError, YahooRetryableError
from app.macro.us_treasury.schemas import TreasurySeries
from app.macro.us_treasury.service import UsTreasuryYieldService
from tests.macro.us_treasury.fixtures import (
    FRED_DGS10_RESPONSE,
    TNX_HISTORY_FRAME,
    ZN_HISTORY_FRAME,
    settings,
)


HISTORY_OPTIONS = {
    "period": "1d",
    "interval": "1m",
    "prepost": False,
    "auto_adjust": False,
    "actions": False,
    "repair": False,
    "keepna": False,
    "raise_errors": True,
}


def _service(*, fred_api_key: str = "fred-key") -> UsTreasuryYieldService:
    return UsTreasuryYieldService(settings=settings(fred_api_key=fred_api_key))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("series", "frame", "symbol"),
    [
        (TreasurySeries.US_10Y, TNX_HISTORY_FRAME, "^TNX"),
        (TreasurySeries.ZN_FUTURE, ZN_HISTORY_FRAME, "ZN=F"),
    ],
)
async def test_collect_intraday_uses_yfinance_history(
    monkeypatch: pytest.MonkeyPatch,
    series: TreasurySeries,
    frame: pd.DataFrame,
    symbol: str,
) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    class FakeTicker:
        def __init__(self, ticker: str) -> None:
            self.ticker = ticker

        def history(self, **kwargs: object) -> pd.DataFrame:
            calls.append((self.ticker, kwargs))
            return frame

    monkeypatch.setattr(service_module.yf, "Ticker", FakeTicker)

    result = await _service().collect_intraday(series)

    assert calls == [(symbol, HISTORY_OPTIONS)]
    assert result.series is series
    assert result.bars


@pytest.mark.asyncio
async def test_collect_intraday_does_not_wrap_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeTicker:
        def __init__(self, _ticker: str) -> None:
            pass

        def history(self, **_kwargs: object) -> pd.DataFrame:
            raise YFRateLimitError

    monkeypatch.setattr(service_module.yf, "Ticker", FakeTicker)

    with pytest.raises(YFRateLimitError):
        await _service().collect_intraday(TreasurySeries.US_10Y)


@pytest.mark.asyncio
async def test_collect_intraday_wraps_other_yfinance_errors_for_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeTicker:
        def __init__(self, _ticker: str) -> None:
            pass

        def history(self, **_kwargs: object) -> pd.DataFrame:
            raise RuntimeError("upstream unavailable")

    monkeypatch.setattr(service_module.yf, "Ticker", FakeTicker)

    with pytest.raises(YahooRetryableError):
        await _service().collect_intraday(TreasurySeries.US_10Y)


@pytest.mark.asyncio
async def test_collect_intraday_raises_when_yfinance_returns_no_bars(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeTicker:
        def __init__(self, _ticker: str) -> None:
            pass

        def history(self, **_kwargs: object) -> pd.DataFrame:
            return TNX_HISTORY_FRAME.iloc[:0]

    monkeypatch.setattr(service_module.yf, "Ticker", FakeTicker)

    with pytest.raises(TreasuryDataUnavailableError):
        await _service().collect_intraday(TreasurySeries.US_10Y)


@pytest.mark.asyncio
async def test_collect_final_does_not_send_yahoo_cookies() -> None:
    # FRED는 별도 쿼터라 Yahoo 세션 쿠키가 새어 나가면 안 된다.
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status.HTTP_200_OK, json=FRED_DGS10_RESPONSE)

    service = _service()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await service.collect_final(TreasurySeries.US_10Y, date(2026, 7, 24), client)

    assert [request.url.host for request in requests] == ["api.stlouisfed.org"]
    assert "cookie" not in requests[0].headers


@pytest.mark.asyncio
async def test_collect_final_calls_fred_with_pinned_observation_window() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status.HTTP_200_OK, json=FRED_DGS10_RESPONSE)

    service = _service()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        observation = await service.collect_final(TreasurySeries.US_10Y, date(2026, 7, 24), client)

    request = requests[0]
    assert request.url.host == "api.stlouisfed.org"
    assert request.url.path == "/fred/series/observations"
    assert dict(request.url.params) == {
        "series_id": "DGS10",
        "api_key": "fred-key",
        "file_type": "json",
        "observation_start": "2026-07-24",
        "observation_end": "2026-07-24",
    }
    assert observation.observation_date == date(2026, 7, 24)
    assert observation.yield_pct == Decimal("4.64")


@pytest.mark.asyncio
async def test_collect_final_requires_api_key_before_calling_fred() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status.HTTP_200_OK, json=FRED_DGS10_RESPONSE)

    service = _service(fred_api_key="")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="FRED_API_KEY"):
            await service.collect_final(TreasurySeries.US_10Y, date(2026, 7, 24), client)

    assert calls == []


@pytest.mark.asyncio
async def test_collect_final_raises_on_upstream_error_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status.HTTP_500_INTERNAL_SERVER_ERROR, request=request, text="internal error")

    service = _service()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await service.collect_final(TreasurySeries.US_10Y, date(2026, 7, 24), client)

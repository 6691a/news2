from datetime import date

import httpx
import pytest
from fastapi import status

from app.instruments.models import Market
from app.ohlcv.exceptions import OhlcvSourceError
from app.ohlcv.korea import KISKoreaDailyChartService
from tests.ohlcv.fixtures import (
    FakeAuth,
    KOREA_DAILY_CHART_ERROR_RESPONSE,
    KOREA_DAILY_CHART_RESPONSE,
    settings,
)


@pytest.mark.asyncio
async def test_collect_daily_sends_adjusted_daily_chart_request() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status.HTTP_200_OK, json=KOREA_DAILY_CHART_RESPONSE)

    auth = FakeAuth()
    service = KISKoreaDailyChartService(settings=settings(), auth=auth)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await service.collect_daily("005930", date(2026, 7, 25), date(2026, 7, 31), client)

    assert auth.call_count == 1
    assert len(requests) == 1
    assert requests[0].url.host == "rest.example"
    assert requests[0].url.path == "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
    assert dict(requests[0].url.params) == {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": "005930",
        "FID_INPUT_DATE_1": "20260725",
        "FID_INPUT_DATE_2": "20260731",
        "FID_PERIOD_DIV_CODE": "D",
        "FID_ORG_ADJ_PRC": "0",
    }
    assert requests[0].headers["tr_id"] == "FHKST03010100"
    assert requests[0].headers["authorization"] == "Bearer access-token"
    assert requests[0].headers["appkey"] == "app-key"
    assert requests[0].headers["custtype"] == "P"
    assert result.ticker == "005930"
    assert result.market is Market.KRX
    assert len(result.bars) == 2


@pytest.mark.asyncio
async def test_collect_daily_splits_long_backfill_into_chunks() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status.HTTP_200_OK, json=KOREA_DAILY_CHART_RESPONSE)

    service = KISKoreaDailyChartService(settings=settings(), auth=FakeAuth())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await service.collect_daily("005930", date(2024, 1, 1), date(2024, 12, 31), client)

    assert len(requests) == 4
    assert requests[0].url.params["FID_INPUT_DATE_1"] == "20240101"
    assert requests[-1].url.params["FID_INPUT_DATE_2"] == "20241231"


@pytest.mark.asyncio
async def test_collect_daily_raises_on_business_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status.HTTP_200_OK, json=KOREA_DAILY_CHART_ERROR_RESPONSE)

    service = KISKoreaDailyChartService(settings=settings(), auth=FakeAuth())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(OhlcvSourceError, match="EGW00201"):
            await service.collect_daily("005930", date(2026, 7, 25), date(2026, 7, 31), client)


@pytest.mark.asyncio
async def test_collect_daily_raises_on_server_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status.HTTP_502_BAD_GATEWAY, text="bad gateway", request=request)

    service = KISKoreaDailyChartService(settings=settings(), auth=FakeAuth())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await service.collect_daily("005930", date(2026, 7, 25), date(2026, 7, 31), client)


@pytest.mark.asyncio
async def test_collect_daily_rejects_virtual_settings() -> None:
    service = KISKoreaDailyChartService(settings=settings(kis_virtual=True), auth=FakeAuth())
    transport = httpx.MockTransport(lambda request: httpx.Response(status.HTTP_200_OK))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(ValueError, match="KIS_VIRTUAL"):
            await service.collect_daily("005930", date(2026, 7, 25), date(2026, 7, 31), client)

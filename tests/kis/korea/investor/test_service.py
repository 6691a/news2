import httpx
import pytest

from app.kis.korea.investor import schemas
from app.kis.korea.investor.schemas import (
    InvestorFlowEnvelope,
    InvestorFlowPhase,
    InvestorFlowProbeOptions,
    InvestorFlowVenue,
    MarketIntradayFlowBody,
    StockIntradayFlowBody,
)
from app.kis.korea.investor.service import KISKoreaInvestorFlowService
from tests.kis.korea.investor.fixtures import INTRADAY_FLOW_RESPONSES, FakeAuth, settings


@pytest.mark.asyncio
async def test_collect_results_calls_intraday_apis_and_returns_typed_bodies() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            headers={
                "tr_cont": "M" if len(requests) == 1 else "",
                "authorization": "response-secret",
            },
            json=INTRADAY_FLOW_RESPONSES[len(requests) - 1],
        )

    auth = FakeAuth()
    options = InvestorFlowProbeOptions(phase=InvestorFlowPhase.INTRADAY)
    service = KISKoreaInvestorFlowService(settings=settings(), auth=auth)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        results = await service.collect_results(options=options, client=client)

    assert auth.call_count == 1
    assert [request.url.path for request in requests] == [
        "/uapi/domestic-stock/v1/quotations/investor-trend-estimate",
        "/uapi/domestic-stock/v1/quotations/investor-trend-estimate",
        "/uapi/domestic-stock/v1/quotations/inquire-investor-time-by-market",
    ]
    assert [dict(request.url.params) for request in requests] == [
        {"MKSC_SHRN_ISCD": "005930"},
        {"MKSC_SHRN_ISCD": "000660"},
        {
            "FID_INPUT_ISCD": "999",
            "FID_INPUT_ISCD_2": "S001",
        },
    ]
    assert [request.headers["tr_id"] for request in requests] == [
        "HHPTJ04160200",
        "HHPTJ04160200",
        "FHPTJ04030000",
    ]
    for request in requests:
        assert request.url.host == "rest.example"
        assert request.headers["authorization"] == "Bearer access-token"
        assert request.headers["appkey"] == "app-key"
        assert request.headers["appsecret"] == "app-secret"
        assert request.headers["custtype"] == "P"
        assert request.headers["tr_cont"] == ""
        assert request.headers["content-type"] == "application/json"
        assert request.headers["accept"] == "text/plain"
        assert request.headers["charset"] == "UTF-8"
        assert request.headers["user-agent"] == (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
        )

    assert [result.venue for result in results] == [
        InvestorFlowVenue.UNSPECIFIED,
        InvestorFlowVenue.UNSPECIFIED,
        InvestorFlowVenue.KRX,
    ]
    assert results[0].tr_cont == "M"
    assert isinstance(results[0].body, StockIntradayFlowBody)
    assert isinstance(results[1].body, StockIntradayFlowBody)
    assert isinstance(results[2].body, MarketIntradayFlowBody)
    assert results[0].body.output2[0].frgn_fake_ntby_qty == 476000
    assert results[0].model_dump(mode="json")["body"] == StockIntradayFlowBody.model_validate(
        INTRADAY_FLOW_RESPONSES[0]
    ).model_dump(mode="json")
    serialized_results = repr(results)
    assert "access-token" not in serialized_results
    assert "app-key" not in serialized_results
    assert "app-secret" not in serialized_results
    assert "response-secret" not in serialized_results


@pytest.mark.asyncio
async def test_collect_results_preserves_kis_error_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            json={
                "rt_cd": "1",
                "msg_cd": "EGW00201",
                "msg1": "초당 거래건수를 초과하였습니다.",
            },
        )

    service = KISKoreaInvestorFlowService(settings=settings(), auth=FakeAuth())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        results = await service.collect_results(
            options=InvestorFlowProbeOptions(phase=InvestorFlowPhase.INTRADAY),
            client=client,
        )

    assert isinstance(results[0].body, InvestorFlowEnvelope)
    assert results[0].body.model_dump(mode="json") == {
        "rt_cd": "1",
        "msg_cd": "EGW00201",
        "msg1": "초당 거래건수를 초과하였습니다.",
    }


@pytest.mark.asyncio
async def test_collect_results_preserves_non_json_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, request=request, text="not json at all")

    service = KISKoreaInvestorFlowService(settings=settings(), auth=FakeAuth())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        results = await service.collect_results(
            options=InvestorFlowProbeOptions(phase=InvestorFlowPhase.INTRADAY),
            client=client,
        )

    assert results[0].http_status == 200
    assert isinstance(results[0].body, schemas.InvestorFlowRawBody)
    assert results[0].body.root == "not json at all"
    assert results[0].model_dump(mode="json")["body"] == "not json at all"


@pytest.mark.asyncio
async def test_collect_results_raises_on_upstream_error_status() -> None:
    """5xx를 빈 결과로 삼키면 Celery 재시도가 돌지 않아 그 슬롯이 영구 누락된다."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, request=request, text="upstream unavailable")

    service = KISKoreaInvestorFlowService(settings=settings(), auth=FakeAuth())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await service.collect_results(
                options=InvestorFlowProbeOptions(phase=InvestorFlowPhase.INTRADAY),
                client=client,
            )


@pytest.mark.asyncio
async def test_collect_results_rejects_virtual_trading_before_issuing_token() -> None:
    auth = FakeAuth()
    service = KISKoreaInvestorFlowService(settings=settings(kis_virtual=True), auth=auth)
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200))) as client:
        with pytest.raises(ValueError, match="KIS_VIRTUAL=false"):
            await service.collect_results(
                options=InvestorFlowProbeOptions(phase=InvestorFlowPhase.INTRADAY),
                client=client,
            )

    assert auth.call_count == 0

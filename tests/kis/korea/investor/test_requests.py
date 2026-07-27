from datetime import date

from app.kis.korea.investor.requests import build_requests
from app.kis.korea.investor.schemas import (
    InvestorFlowPhase,
    InvestorFlowProbeOptions,
    InvestorFlowScope,
    InvestorFlowTrId,
    InvestorFlowVenue,
)


def test_build_intraday_requests_distinguishes_stock_scope_from_kospi_krx() -> None:
    options = InvestorFlowProbeOptions(phase=InvestorFlowPhase.INTRADAY)

    requests = build_requests(options)

    assert [(item.target, item.venue, item.tr_id, item.params) for item in requests] == [
        (
            "005930",
            InvestorFlowVenue.UNSPECIFIED,
            "HHPTJ04160200",
            {"MKSC_SHRN_ISCD": "005930"},
        ),
        (
            "000660",
            InvestorFlowVenue.UNSPECIFIED,
            "HHPTJ04160200",
            {"MKSC_SHRN_ISCD": "000660"},
        ),
        (
            "KOSPI",
            InvestorFlowVenue.KRX,
            "FHPTJ04030000",
            {
                "FID_INPUT_ISCD": "999",
                "FID_INPUT_ISCD_2": "S001",
            },
        ),
    ]


def test_scope_splits_stock_and_market_requests() -> None:
    # 두 TR의 갱신 주기가 달라 beat 스케줄이 분리되어 있다. scope가 실제로
    # 요청을 갈라놓지 못하면 한쪽은 반드시 틀린 주기로 호출된다.
    stock_only = build_requests(
        InvestorFlowProbeOptions(phase=InvestorFlowPhase.INTRADAY, scope=InvestorFlowScope.STOCK)
    )
    market_only = build_requests(
        InvestorFlowProbeOptions(phase=InvestorFlowPhase.INTRADAY, scope=InvestorFlowScope.MARKET)
    )

    assert [item.target for item in stock_only] == ["005930", "000660"]
    assert all(item.tr_id is InvestorFlowTrId.STOCK_INTRADAY for item in stock_only)
    assert [item.target for item in market_only] == ["KOSPI"]
    assert all(item.tr_id is InvestorFlowTrId.KOSPI_INTRADAY for item in market_only)


def test_scope_splits_final_requests_too() -> None:
    options = InvestorFlowProbeOptions(
        phase=InvestorFlowPhase.FINAL,
        scope=InvestorFlowScope.MARKET,
        trade_date=date(2026, 7, 21),
    )

    requests = build_requests(options)

    assert [item.target for item in requests] == ["KOSPI"]
    assert requests[0].tr_id is InvestorFlowTrId.KOSPI_FINAL


def test_build_final_requests_separates_krx_and_nxt_for_each_stock() -> None:
    options = InvestorFlowProbeOptions(
        phase=InvestorFlowPhase.FINAL,
        trade_date=date(2026, 7, 21),
    )

    requests = build_requests(options)

    assert [(item.target, item.venue, item.params) for item in requests] == [
        (
            "005930",
            InvestorFlowVenue.KRX,
            {
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": "005930",
                "FID_INPUT_DATE_1": "20260721",
                "FID_ORG_ADJ_PRC": "",
                "FID_ETC_CLS_CODE": "",
            },
        ),
        (
            "005930",
            InvestorFlowVenue.NXT,
            {
                "FID_COND_MRKT_DIV_CODE": "NX",
                "FID_INPUT_ISCD": "005930",
                "FID_INPUT_DATE_1": "20260721",
                "FID_ORG_ADJ_PRC": "",
                "FID_ETC_CLS_CODE": "",
            },
        ),
        (
            "000660",
            InvestorFlowVenue.KRX,
            {
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": "000660",
                "FID_INPUT_DATE_1": "20260721",
                "FID_ORG_ADJ_PRC": "",
                "FID_ETC_CLS_CODE": "",
            },
        ),
        (
            "000660",
            InvestorFlowVenue.NXT,
            {
                "FID_COND_MRKT_DIV_CODE": "NX",
                "FID_INPUT_ISCD": "000660",
                "FID_INPUT_DATE_1": "20260721",
                "FID_ORG_ADJ_PRC": "",
                "FID_ETC_CLS_CODE": "",
            },
        ),
        (
            "KOSPI",
            InvestorFlowVenue.KRX,
            {
                "FID_COND_MRKT_DIV_CODE": "U",
                "FID_INPUT_ISCD": "0001",
                "FID_INPUT_DATE_1": "20260721",
                "FID_INPUT_ISCD_1": "KSP",
                "FID_INPUT_DATE_2": "20260721",
                "FID_INPUT_ISCD_2": "0001",
            },
        ),
    ]

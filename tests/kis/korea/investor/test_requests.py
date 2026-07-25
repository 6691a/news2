from datetime import date

from app.kis.korea.investor.requests import build_requests
from app.kis.korea.investor.schemas import (
    InvestorFlowPhase,
    InvestorFlowProbeOptions,
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

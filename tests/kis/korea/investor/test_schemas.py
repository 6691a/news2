from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.kis.korea.investor import schemas
from app.kis.korea.investor.schemas import (
    InvestorFlowPhase,
    InvestorFlowProbeOptions,
    InvestorFlowTrId,
    MarketIntradayFlowBody,
    MarketIntradayFlowRow,
    StockIntradayFlowBody,
    StockIntradayFlowRow,
)
from tests.kis.korea.investor.fixtures import (
    MARKET_FINAL_FLOW_RESPONSE,
    MARKET_INTRADAY_FLOW_RESPONSE,
    STOCK_FINAL_FLOW_RESPONSES,
    STOCK_INTRADAY_FLOW_RESPONSES,
)


def test_final_options_require_a_real_calendar_date() -> None:
    with pytest.raises(ValidationError):
        InvestorFlowProbeOptions(phase=InvestorFlowPhase.FINAL)

    with pytest.raises(ValidationError):
        InvestorFlowProbeOptions(
            phase=InvestorFlowPhase.FINAL,
            trade_date="2026-02-30",
        )


@pytest.mark.parametrize("response", STOCK_INTRADAY_FLOW_RESPONSES)
def test_stock_intraday_flow_body_parses_real_response(response: dict[str, object]) -> None:
    body = StockIntradayFlowBody.model_validate(response)

    assert body.rt_cd == "0"
    assert len(body.output2) == 4
    assert set(StockIntradayFlowRow.model_fields) == set(response["output2"][0])
    assert all(
        isinstance(value, int)
        for row in body.output2
        for value in (
            row.frgn_fake_ntby_qty,
            row.orgn_fake_ntby_qty,
            row.sum_fake_ntby_qty,
        )
    )


def test_market_intraday_flow_body_parses_every_real_response_field() -> None:
    body = MarketIntradayFlowBody.model_validate(MARKET_INTRADAY_FLOW_RESPONSE)
    row = body.output[0]

    assert body.msg_cd == "MCA00000"
    assert set(MarketIntradayFlowRow.model_fields) == set(MARKET_INTRADAY_FLOW_RESPONSE["output"][0])
    assert all(isinstance(value, int) for value in row.model_dump().values())
    assert row.frgn_ntby_qty == -100609
    assert row.orgn_ntby_tr_pbmn == 30791


def test_market_final_flow_body_parses_every_real_response_field() -> None:
    body = schemas.parse_investor_flow_body(
        InvestorFlowTrId.KOSPI_FINAL,
        MARKET_FINAL_FLOW_RESPONSE,
    )

    assert isinstance(body, schemas.MarketFinalFlowBody)
    row = body.output[0]
    assert set(type(row).model_fields) == set(MARKET_FINAL_FLOW_RESPONSE["output"][0])
    assert row.stck_bsop_date == "20260724"
    assert row.bstp_nmix_prpr == Decimal("6690.62")
    assert row.frgn_ntby_qty == -18722
    assert row.orgn_ntby_tr_pbmn == -1951441


def test_stock_final_flow_body_parses_every_real_response_field() -> None:
    response = STOCK_FINAL_FLOW_RESPONSES[0]

    body = schemas.parse_investor_flow_body(InvestorFlowTrId.STOCK_FINAL, response)

    assert isinstance(body, schemas.StockFinalFlowBody)
    assert set(type(body.output1).model_fields) == set(response["output1"])
    assert set(type(body.output2[0]).model_fields) == set(response["output2"][0])
    assert body.output1.prdy_ctrt == Decimal("1.00")
    assert body.output2[0].stck_bsop_date == "20260724"
    assert body.output2[0].stck_clpr == 249500
    assert body.output2[0].frgn_ntby_tr_pbmn == -867979


def test_non_kis_json_error_uses_pydantic_raw_fallback() -> None:
    response = {"detail": "bad gateway"}

    body = schemas.parse_investor_flow_body(InvestorFlowTrId.STOCK_INTRADAY, response)

    assert isinstance(body, schemas.InvestorFlowRawBody)
    assert body.root == response

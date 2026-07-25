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
    MARKET_INTRADAY_FLOW_RESPONSE,
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
    assert row.frgn_ntby_qty == -32845
    assert row.orgn_ntby_tr_pbmn == -1399396


def test_unmodeled_final_body_uses_pydantic_raw_fallback() -> None:
    response = {
        "rt_cd": "0",
        "msg_cd": "MCA00000",
        "msg1": "정상처리 되었습니다.",
        "output1": [{"unmodeled": "value"}],
    }

    body = schemas.parse_investor_flow_body(InvestorFlowTrId.STOCK_FINAL, response)

    assert isinstance(body, schemas.InvestorFlowRawBody)
    assert body.root == response


def test_non_kis_json_error_uses_pydantic_raw_fallback() -> None:
    response = {"detail": "bad gateway"}

    body = schemas.parse_investor_flow_body(InvestorFlowTrId.STOCK_INTRADAY, response)

    assert isinstance(body, schemas.InvestorFlowRawBody)
    assert body.root == response

import logging
from copy import deepcopy
from datetime import date
from decimal import Decimal
from typing import cast

import pytest
from pydantic import ValidationError

from app.kis.korea.investor import schemas
from app.kis.korea.investor.schemas import (
    InvestorFlowPhase,
    InvestorFlowProbeOptions,
    InvestorFlowRequest,
    InvestorFlowTrId,
    InvestorFlowVenue,
    InvestorType,
    MarketFinalFlowParams,
    MarketIntradayFlowBody,
    MarketIntradayFlowParams,
    MarketIntradayFlowRow,
    StockFinalFlowParams,
    StockIntradayFlowBody,
    StockIntradayFlowParams,
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
    assert all(isinstance(getattr(row, field_name), int) for field_name in MarketIntradayFlowRow.model_fields)
    assert row.frgn_ntby_qty == -100609
    assert row.orgn_ntby_tr_pbmn == 30791


def test_market_intraday_values_for_maps_all_investor_types() -> None:
    row = MarketIntradayFlowBody.model_validate(MARKET_INTRADAY_FLOW_RESPONSE).output[0]

    assert {
        investor_type: (
            row.values_for(investor_type).net_buy_volume,
            row.values_for(investor_type).net_buy_value,
            row.values_for(investor_type).reports_investor,
        )
        for investor_type in InvestorType
    } == {
        InvestorType.FOREIGN: (-100609, -201498, True),
        InvestorType.RETAIL: (51192, 163565, True),
        InvestorType.INSTITUTION: (45228, 30791, True),
        InvestorType.SECURITIES: (32061, 25253, True),
        InvestorType.TRUST: (12136, -29664, True),
        InvestorType.PRIVATE_EQUITY: (0, 0, False),
        InvestorType.BANK: (0, 0, False),
        InvestorType.INSURANCE: (-178, -858, True),
        InvestorType.MERCHANT_BANK: (0, 0, False),
        InvestorType.PENSION_FUND: (1209, 36059, True),
        InvestorType.OTHER_ORGANIZATION: (0, 0, False),
        InvestorType.OTHER_CORPORATION: (4189, 7143, True),
    }


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


@pytest.mark.parametrize(
    ("tr_id", "params"),
    [
        (InvestorFlowTrId.STOCK_INTRADAY, MarketIntradayFlowParams(market_code="999", industry_code="S001")),
        (
            InvestorFlowTrId.KOSPI_FINAL,
            StockFinalFlowParams(
                market_code="J",
                stock_code="005930",
                trade_date="20260724",
                original_adjusted_price="",
                other_classification_code="",
            ),
        ),
    ],
)
def test_investor_flow_request_rejects_params_for_another_tr(
    tr_id: InvestorFlowTrId,
    params: StockIntradayFlowParams | MarketIntradayFlowParams | StockFinalFlowParams | MarketFinalFlowParams,
) -> None:
    with pytest.raises(ValidationError):
        InvestorFlowRequest(
            target="005930",
            target_name="삼성전자",
            venue=InvestorFlowVenue.KRX,
            tr_id=tr_id,
            params=params,
        )


def test_non_kis_json_error_is_rejected() -> None:
    with pytest.raises(ValidationError):
        schemas.parse_investor_flow_body(
            InvestorFlowTrId.STOCK_INTRADAY,
            {"detail": "bad gateway"},
        )


def test_non_json_body_uses_typed_text_fallback() -> None:
    body = schemas.parse_investor_flow_body(
        InvestorFlowTrId.STOCK_INTRADAY,
        "not json at all",
    )

    assert isinstance(body, schemas.InvestorFlowTextBody)
    assert body.root == "not json at all"


def test_trade_dates_returns_single_day_without_backfill() -> None:
    options = InvestorFlowProbeOptions(phase=InvestorFlowPhase.FINAL, trade_date=date(2026, 7, 30))

    assert options.trade_dates() == (date(2026, 7, 30),)


def test_trade_dates_skips_weekends_over_backfill_range() -> None:
    # 2025-01-03(금) ~ 2025-01-06(월). 주말 이틀은 응답이 비어 있어 미리 걸러낸다.
    options = InvestorFlowProbeOptions(
        phase=InvestorFlowPhase.FINAL,
        start_date=date(2025, 1, 3),
        trade_date=date(2025, 1, 6),
    )

    assert options.trade_dates() == (date(2025, 1, 3), date(2025, 1, 6))


def test_trade_dates_is_empty_for_intraday() -> None:
    assert InvestorFlowProbeOptions(phase=InvestorFlowPhase.INTRADAY).trade_dates() == ()


def test_intraday_options_reject_backfill_range() -> None:
    with pytest.raises(ValidationError, match="does not accept start_date"):
        InvestorFlowProbeOptions(phase=InvestorFlowPhase.INTRADAY, start_date=date(2025, 1, 1))


def test_backfill_options_reject_reversed_period() -> None:
    with pytest.raises(ValidationError, match="must not be after"):
        InvestorFlowProbeOptions(
            phase=InvestorFlowPhase.FINAL,
            start_date=date(2026, 7, 31),
            trade_date=date(2025, 1, 1),
        )


def test_stock_final_body_drops_blank_padding_rows(caplog: pytest.LogCaptureFixture) -> None:
    # NXT 출범 전 날짜처럼 데이터가 없는 구간에서는 KIS가 영업일자만 채우고 나머지를
    # 전부 빈 문자열로 보낸다. 두면 숫자 파싱이 통째로 깨져 그 날짜 수집이 죽는다.
    payload = deepcopy(STOCK_FINAL_FLOW_RESPONSES[0])
    rows = cast("list[dict[str, str]]", payload["output2"])
    rows.append({key: ("20241118" if key == "stck_bsop_date" else "") for key in rows[0]})

    with caplog.at_level(logging.WARNING):
        body = schemas.StockFinalFlowBody.model_validate(payload)

    assert len(body.output2) == len(rows) - 1
    assert "investor_flow_blank_rows_dropped" in caplog.text

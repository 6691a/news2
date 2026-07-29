from copy import deepcopy
from datetime import UTC, date, datetime
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.kis.korea.investor.repository import (
    KISInvestorFlowRepository,
    snapshot_slot_start,
    to_flow_rows,
)
from app.kis.korea.investor.schemas import (
    InvestorFlowPhase,
    InvestorFlowProbeOptions,
    InvestorFlowResult,
    InvestorFlowTrId,
    InvestorFlowVenue,
    InvestorType,
    parse_investor_flow_body,
)
from tests.kis.korea.investor.fixtures import (
    MARKET_FINAL_FLOW_RESPONSE,
    MARKET_INTRADAY_FLOW_RESPONSE,
    STOCK_FINAL_FLOW_RESPONSES,
    STOCK_INTRADAY_FLOW_RESPONSES,
)


# 한국 기준 다음 날 00:40 — UTC 날짜(7/24)와 KST 날짜(7/25)가 갈리는 시각.
SNAPSHOT_TS = datetime(2026, 7, 24, 15, 40, tzinfo=UTC)
INTRADAY_OPTIONS = InvestorFlowProbeOptions(phase=InvestorFlowPhase.INTRADAY)
FINAL_OPTIONS = InvestorFlowProbeOptions(
    phase=InvestorFlowPhase.FINAL,
    trade_date=date(2026, 7, 24),
)


def _execute_result(rows: list[tuple[object, ...]]) -> MagicMock:
    result = MagicMock()
    result.all.return_value = rows
    return result


def _result(
    target: str,
    venue: InvestorFlowVenue,
    tr_id: InvestorFlowTrId,
    response: dict[str, object],
) -> InvestorFlowResult:
    return InvestorFlowResult(
        target=target,
        target_name=target,
        venue=venue,
        tr_id=tr_id,
        http_status=200,
        tr_cont="",
        body=parse_investor_flow_body(tr_id, response),
    )


def test_stock_intraday_flow_expands_to_two_rows_per_time_bucket() -> None:
    result = _result(
        "005930",
        InvestorFlowVenue.UNSPECIFIED,
        InvestorFlowTrId.STOCK_INTRADAY,
        STOCK_INTRADAY_FLOW_RESPONSES[0],
    )

    rows = to_flow_rows(result, INTRADAY_OPTIONS, instrument_id=1, snapshot_ts=SNAPSHOT_TS)

    assert len(rows) == 8
    assert {row.time_bucket for row in rows} == {"1", "2", "3", "4"}
    assert all(row.is_provisional for row in rows)
    # 장중 응답에는 날짜가 없다. UTC 날짜(7/24)가 아니라 KST 날짜여야 한다.
    assert all(row.trade_date == date(2026, 7, 25) for row in rows)

    bucket_4 = {row.investor_type: row for row in rows if row.time_bucket == "4"}
    assert bucket_4[InvestorType.FOREIGN].net_buy_volume == 476000
    assert bucket_4[InvestorType.INSTITUTION].net_buy_volume == 1164000
    # 종목 장중 TR은 금액을 주지 않는다.
    assert bucket_4[InvestorType.FOREIGN].net_buy_value is None
    assert bucket_4[InvestorType.FOREIGN].details["sum_fake_ntby_qty"] == 1640000


def test_market_intraday_flow_maps_every_investor_type_and_preserves_raw_values() -> None:
    result = _result(
        "KOSPI",
        InvestorFlowVenue.KRX,
        InvestorFlowTrId.KOSPI_INTRADAY,
        MARKET_INTRADAY_FLOW_RESPONSE,
    )

    rows = to_flow_rows(result, INTRADAY_OPTIONS, instrument_id=2, snapshot_ts=SNAPSHOT_TS)

    # 장중 TR이 채우는 유형은 접미사가 qty/vol로 갈려도 누락되지 않아야 한다.
    assert {row.investor_type for row in rows} == {
        InvestorType.FOREIGN,
        InvestorType.RETAIL,
        InvestorType.INSTITUTION,
        InvestorType.SECURITIES,
        InvestorType.TRUST,
        InvestorType.INSURANCE,
        InvestorType.PENSION_FUND,
        InvestorType.OTHER_CORPORATION,
    }
    assert all(row.time_bucket == "" for row in rows)

    by_type = {row.investor_type: row for row in rows}
    assert by_type[InvestorType.FOREIGN].net_buy_volume == -100609
    # 거래대금 단위가 확정될 때까지 KIS 원본값을 그대로 저장한다.
    assert by_type[InvestorType.FOREIGN].net_buy_value == -201498
    assert by_type[InvestorType.FOREIGN].details["seln_vol"] == 1101035


def test_market_intraday_flow_drops_investor_types_the_tr_never_fills() -> None:
    """FHPTJ04030000이 6개 필드를 모두 0으로 주는 유형은 0으로 저장하지 않는다."""

    result = _result(
        "KOSPI",
        InvestorFlowVenue.KRX,
        InvestorFlowTrId.KOSPI_INTRADAY,
        MARKET_INTRADAY_FLOW_RESPONSE,
    )

    rows = to_flow_rows(result, INTRADAY_OPTIONS, instrument_id=2, snapshot_ts=SNAPSHOT_TS)

    stored = {row.investor_type for row in rows}
    assert InvestorType.PRIVATE_EQUITY not in stored
    assert InvestorType.BANK not in stored
    assert InvestorType.MERCHANT_BANK not in stored
    assert InvestorType.OTHER_ORGANIZATION not in stored
    # 매수가 0이어도 매도가 있으면 실제 집계이므로 남는다.
    assert InvestorType.INSURANCE in stored


def test_stock_final_flow_maps_requested_day_to_every_investor_type() -> None:
    response = deepcopy(STOCK_FINAL_FLOW_RESPONSES[0])
    historical_row = deepcopy(response["output2"][0])
    historical_row["stck_bsop_date"] = "20260723"
    response["output2"].append(historical_row)
    result = _result(
        "005930",
        InvestorFlowVenue.KRX,
        InvestorFlowTrId.STOCK_FINAL,
        response,
    )

    rows = to_flow_rows(
        result,
        FINAL_OPTIONS,
        instrument_id=1,
        snapshot_ts=SNAPSHOT_TS,
    )

    assert len(rows) == len(InvestorType)
    assert {row.investor_type for row in rows} == set(InvestorType)
    assert all(row.trade_date == date(2026, 7, 24) for row in rows)
    assert all(row.time_bucket == "" for row in rows)
    assert not any(row.is_provisional for row in rows)
    securities = next(row for row in rows if row.investor_type is InvestorType.SECURITIES)
    assert securities.net_buy_volume == -1877953
    assert securities.net_buy_value == -480862
    assert securities.details == {
        "seln_vol": 2948483,
        "shnu_vol": 1070530,
        "seln_tr_pbmn": 749947,
        "shnu_tr_pbmn": 269086,
    }


def test_market_final_flow_maps_every_investor_type() -> None:
    result = _result(
        "KOSPI",
        InvestorFlowVenue.KRX,
        InvestorFlowTrId.KOSPI_FINAL,
        MARKET_FINAL_FLOW_RESPONSE,
    )

    rows = to_flow_rows(
        result,
        FINAL_OPTIONS,
        instrument_id=2,
        snapshot_ts=SNAPSHOT_TS,
    )

    assert len(rows) == len(InvestorType)
    assert {row.investor_type for row in rows} == set(InvestorType)
    assert all(row.trade_date == date(2026, 7, 24) for row in rows)
    assert all(row.time_bucket == "" for row in rows)
    assert not any(row.is_provisional for row in rows)
    securities = next(row for row in rows if row.investor_type is InvestorType.SECURITIES)
    assert securities.net_buy_volume == -3940
    assert securities.net_buy_value == -873973
    assert securities.details == {}


def test_final_options_pin_trade_date_and_clear_provisional_flag() -> None:
    options = InvestorFlowProbeOptions(
        phase=InvestorFlowPhase.FINAL,
        trade_date=date(2026, 7, 20),
    )
    result = _result(
        "KOSPI",
        InvestorFlowVenue.KRX,
        InvestorFlowTrId.KOSPI_INTRADAY,
        MARKET_INTRADAY_FLOW_RESPONSE,
    )

    rows = to_flow_rows(result, options, instrument_id=2, snapshot_ts=SNAPSHOT_TS)

    assert all(row.trade_date == date(2026, 7, 20) for row in rows)
    assert not any(row.is_provisional for row in rows)


def test_snapshot_slot_start_pins_retries_to_the_same_timestamp() -> None:
    # 같은 30분 슬롯 안의 재시도는 같은 snapshot_ts를 써야 중복 저장이 안 된다.
    first_try = datetime(2026, 7, 24, 6, 0, 3, 500, tzinfo=UTC)
    retry = datetime(2026, 7, 24, 6, 29, 59, tzinfo=UTC)
    next_slot = datetime(2026, 7, 24, 6, 30, 1, tzinfo=UTC)

    assert snapshot_slot_start(first_try) == datetime(2026, 7, 24, 6, 0, tzinfo=UTC)
    assert snapshot_slot_start(retry) == snapshot_slot_start(first_try)
    assert snapshot_slot_start(next_slot) == datetime(2026, 7, 24, 6, 30, tzinfo=UTC)


def test_error_envelope_produces_no_rows() -> None:
    result = _result(
        "005930",
        InvestorFlowVenue.UNSPECIFIED,
        InvestorFlowTrId.STOCK_INTRADAY,
        {"rt_cd": "1", "msg_cd": "EGW00121", "msg1": "유효하지 않은 종목코드입니다."},
    )

    assert to_flow_rows(result, INTRADAY_OPTIONS, instrument_id=1, snapshot_ts=SNAPSHOT_TS) == []


@pytest.mark.asyncio
async def test_save_skips_only_the_venue_already_stored_in_the_slot() -> None:
    """KRX만 저장된 부분 성공 상태에서 재실행하면 NXT는 복구돼야 한다."""

    results = (
        _result("005930", InvestorFlowVenue.KRX, InvestorFlowTrId.STOCK_FINAL, STOCK_FINAL_FLOW_RESPONSES[0]),
        _result("005930", InvestorFlowVenue.NXT, InvestorFlowTrId.STOCK_FINAL, STOCK_FINAL_FLOW_RESPONSES[0]),
    )
    session = AsyncMock(spec=AsyncSession)
    session.execute.side_effect = [
        _execute_result([(1, InvestorFlowVenue.KRX)]),  # 이미 저장된 (instrument, venue)
        _execute_result([("005930", 1)]),  # ticker -> instrument_id
    ]
    session.add_all = MagicMock()
    session_context = AsyncMock()
    session_context.__aenter__.return_value = session
    session_factory = MagicMock(spec=async_sessionmaker)
    session_factory.begin.return_value = session_context
    repository = KISInvestorFlowRepository(cast("async_sessionmaker[AsyncSession]", session_factory))

    saved = await repository.save(results, FINAL_OPTIONS, SNAPSHOT_TS)

    rows = session.add_all.call_args.args[0]
    assert saved == len(rows) == len(InvestorType)
    assert {row.venue for row in rows} == {InvestorFlowVenue.NXT}

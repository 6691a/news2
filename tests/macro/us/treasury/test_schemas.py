from copy import deepcopy
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError
from structlog.testing import capture_logs

from app.macro.us.treasury.exceptions import TreasuryDataUnavailableError
from app.macro.us.treasury.schemas import (
    FredObservationsEnvelope,
    FredObservationsRequest,
    TreasuryPhase,
    TreasuryProbeOptions,
    TreasurySeries,
    parse_fred_observations,
    parse_fred_response,
    parse_history_frame,
)
from tests.macro.us.treasury.fixtures import (
    FRED_DGS10_EMPTY_RESPONSE,
    FRED_DGS10_MISSING_RESPONSE,
    FRED_DGS10_RESPONSE,
    TNX_HISTORY_FRAME,
    ZN_HISTORY_FRAME,
)


# ^TNX 샘플의 마지막 봉(12:22)이 끝난 뒤 시각.
TNX_AS_OF = datetime(2026, 7, 27, 12, 25, tzinfo=UTC)
# ZN=F 샘플의 마지막 봉(04:03)이 끝난 뒤 시각.
ZN_AS_OF = datetime(2026, 7, 28, 4, 6, tzinfo=UTC)
TARGET_DATE = date(2026, 7, 24)


def test_external_requests_serialize_wire_parameters() -> None:
    assert FredObservationsRequest(
        series_id="DGS10",
        api_key="fred-key",
        observation_start=TARGET_DATE,
        observation_end=TARGET_DATE,
    ).model_dump(mode="json") == {
        "series_id": "DGS10",
        "api_key": "fred-key",
        "file_type": "json",
        "observation_start": "2026-07-24",
        "observation_end": "2026-07-24",
    }


def test_parse_history_frame_keeps_yield_percent_and_utc_bar_start() -> None:
    result = parse_history_frame(TreasurySeries.US_10Y, TNX_HISTORY_FRAME, as_of=TNX_AS_OF)

    assert result.series is TreasurySeries.US_10Y
    assert [bar.event_ts for bar in result.bars] == [
        datetime(2026, 7, 27, 12, 20, tzinfo=UTC),
        datetime(2026, 7, 27, 12, 21, tzinfo=UTC),
        datetime(2026, 7, 27, 12, 22, tzinfo=UTC),
    ]
    # 수익률은 % 원본 그대로다. bp 환산은 조회하는 쪽의 몫이다.
    assert result.bars[0].close == Decimal("4.647000312805176")
    assert result.bars[2].close == Decimal("4.640999794006348")
    assert result.bars[2].open == Decimal("4.647000312805176")
    assert result.bars[2].high == Decimal("4.64900016784668")
    assert result.bars[2].low == Decimal("4.638999938964844")


def test_parse_history_frame_reads_futures_fraction_price_without_loss() -> None:
    result = parse_history_frame(TreasurySeries.ZN_FUTURE, ZN_HISTORY_FRAME, as_of=ZN_AS_OF)

    assert result.series is TreasurySeries.ZN_FUTURE
    # 1/64 포인트 분수 가격이 Decimal로 그대로 보존돼야 한다.
    assert result.bars[0].close == Decimal("108.65625")
    assert result.bars[2].close == Decimal("108.671875")
    assert result.bars[2].high == Decimal("108.671875")
    # volume 같은 추가 필드는 DTO에 없어 무시된다.
    assert not hasattr(result.bars[0], "volume")


def test_parse_history_frame_drops_bars_without_close() -> None:
    result = parse_history_frame(TreasurySeries.ZN_FUTURE, ZN_HISTORY_FRAME, as_of=ZN_AS_OF)

    # 거래가 없던 04:03 봉은 close가 null이라 버린다.
    assert [bar.event_ts for bar in result.bars] == [
        datetime(2026, 7, 28, 4, 0, tzinfo=UTC),
        datetime(2026, 7, 28, 4, 1, tzinfo=UTC),
        datetime(2026, 7, 28, 4, 2, tzinfo=UTC),
    ]


def test_parse_history_frame_drops_the_bar_still_in_progress() -> None:
    # 12:22 봉은 12:23이 되어야 확정된다. 저장하면 다음 회차가 갱신하지 못한다.
    as_of = datetime(2026, 7, 27, 12, 22, 30, tzinfo=UTC)
    result = parse_history_frame(TreasurySeries.US_10Y, TNX_HISTORY_FRAME, as_of=as_of)

    assert [bar.event_ts for bar in result.bars] == [
        datetime(2026, 7, 27, 12, 20, tzinfo=UTC),
        datetime(2026, 7, 27, 12, 21, tzinfo=UTC),
    ]


def test_parse_history_frame_logs_dropped_and_parsed_counts() -> None:
    with capture_logs() as logs:
        result = parse_history_frame(TreasurySeries.ZN_FUTURE, ZN_HISTORY_FRAME, as_of=ZN_AS_OF)

    dropped = [entry for entry in logs if entry["event"] == "treasury_intraday_rows_without_close"]
    assert len(dropped) == 1
    assert dropped[0]["log_level"] == "warning"
    assert dropped[0]["dropped"] == 1

    parsed = [entry for entry in logs if entry["event"] == "treasury_intraday_parsed"]
    assert len(parsed) == 1
    assert parsed[0]["series"] == "ZN"
    # 버린 행까지 더하면 응답 건수가 나와야 한다. 하나라도 어긋나면 조용히 사라진 행이 있다.
    assert parsed[0]["received"] == len(ZN_HISTORY_FRAME.index)
    assert parsed[0]["parsed"] + parsed[0]["skipped_unsettled"] + dropped[0]["dropped"] == parsed[0]["received"]
    assert parsed[0]["parsed"] == len(result.bars)


def test_parse_history_frame_logs_unsettled_bars_without_warning() -> None:
    # 12:22 봉은 아직 진행 중이다. 정상 동작이라 warning이 아니라 건수로만 남는다.
    as_of = datetime(2026, 7, 27, 12, 22, 30, tzinfo=UTC)

    with capture_logs() as logs:
        parse_history_frame(TreasurySeries.US_10Y, TNX_HISTORY_FRAME, as_of=as_of)

    assert not [entry for entry in logs if entry["event"] == "treasury_intraday_rows_without_close"]
    parsed = [entry for entry in logs if entry["event"] == "treasury_intraday_parsed"]
    assert (parsed[0]["received"], parsed[0]["parsed"], parsed[0]["skipped_unsettled"]) == (3, 2, 1)


def test_parse_history_frame_logs_zero_parsed_when_everything_is_filtered() -> None:
    # 응답은 왔는데 전부 걸러진 상태. 서비스는 frame.empty가 아니라 예외를 올리지 않는다.
    as_of = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)

    with capture_logs() as logs:
        result = parse_history_frame(TreasurySeries.US_10Y, TNX_HISTORY_FRAME, as_of=as_of)

    assert result.bars == ()
    parsed = [entry for entry in logs if entry["event"] == "treasury_intraday_parsed"]
    assert (parsed[0]["received"], parsed[0]["parsed"]) == (3, 0)


def test_parse_history_frame_rejects_naive_index() -> None:
    frame = TNX_HISTORY_FRAME.copy()
    frame.index = frame.index.tz_localize(None)

    with pytest.raises(ValueError, match="timezone-aware"):
        parse_history_frame(TreasurySeries.US_10Y, frame, as_of=TNX_AS_OF)


def test_parse_history_frame_rejects_missing_ohlc_column() -> None:
    frame = TNX_HISTORY_FRAME.drop(columns="Close")

    with pytest.raises(ValueError, match="Close"):
        parse_history_frame(TreasurySeries.US_10Y, frame, as_of=TNX_AS_OF)


def test_parse_fred_response_reads_target_date_observation_and_metadata() -> None:
    response = FredObservationsEnvelope.model_validate(FRED_DGS10_RESPONSE)

    observation = parse_fred_response(TreasurySeries.US_10Y, TARGET_DATE, response)

    assert response.realtime_start == date(2026, 7, 28)
    assert response.observation_start == TARGET_DATE
    assert response.count == 1
    assert response.observations[0].realtime_end == date(2026, 7, 28)
    assert observation.series is TreasurySeries.US_10Y
    assert observation.observation_date == TARGET_DATE
    assert observation.yield_pct == Decimal("4.64")


def test_parse_fred_response_raises_when_value_is_missing_marker() -> None:
    response = FredObservationsEnvelope.model_validate(FRED_DGS10_MISSING_RESPONSE)

    with pytest.raises(TreasuryDataUnavailableError):
        parse_fred_response(TreasurySeries.US_10Y, TARGET_DATE, response)


def test_parse_fred_response_raises_when_observations_are_empty() -> None:
    response = FredObservationsEnvelope.model_validate(FRED_DGS10_EMPTY_RESPONSE)

    with pytest.raises(TreasuryDataUnavailableError):
        parse_fred_response(TreasurySeries.US_10Y, TARGET_DATE, response)


def test_parse_fred_response_raises_when_another_date_is_returned() -> None:
    response = FredObservationsEnvelope.model_validate(deepcopy(FRED_DGS10_RESPONSE))

    with pytest.raises(TreasuryDataUnavailableError):
        parse_fred_response(TreasurySeries.US_10Y, date(2026, 7, 23), response)


def test_final_options_require_target_date() -> None:
    with pytest.raises(ValidationError):
        TreasuryProbeOptions(phase=TreasuryPhase.FINAL)


def test_final_options_reject_futures_series() -> None:
    # ZN 선물은 무료로 얻을 수 있는 공식 정산가가 없어 확정치 경로가 없다.
    with pytest.raises(ValidationError):
        TreasuryProbeOptions(
            phase=TreasuryPhase.FINAL,
            series=TreasurySeries.ZN_FUTURE,
            target_date=TARGET_DATE,
        )


def test_intraday_options_reject_target_date() -> None:
    with pytest.raises(ValidationError):
        TreasuryProbeOptions(phase=TreasuryPhase.INTRADAY, target_date=TARGET_DATE)


def test_series_maps_to_source_identifiers() -> None:
    assert TreasurySeries.US_10Y.yahoo_symbol == "^TNX"
    assert TreasurySeries.US_10Y.fred_series_id == "DGS10"
    assert TreasurySeries.ZN_FUTURE.yahoo_symbol == "ZN=F"

    with pytest.raises(ValueError):
        _ = TreasurySeries.ZN_FUTURE.fred_series_id


def test_backfill_options_require_period() -> None:
    with pytest.raises(ValidationError, match="requires start_date"):
        TreasuryProbeOptions(phase=TreasuryPhase.BACKFILL, target_date=date(2026, 7, 31))


def test_backfill_options_reject_reversed_period() -> None:
    with pytest.raises(ValidationError, match="must not be after"):
        TreasuryProbeOptions(
            phase=TreasuryPhase.BACKFILL,
            start_date=date(2026, 7, 31),
            target_date=date(2025, 1, 1),
        )


def test_final_options_reject_start_date() -> None:
    with pytest.raises(ValidationError, match="does not accept start_date"):
        TreasuryProbeOptions(
            phase=TreasuryPhase.FINAL,
            start_date=date(2025, 1, 1),
            target_date=date(2026, 7, 31),
        )


def test_parse_fred_observations_skips_missing_values_and_sorts() -> None:
    envelope = FredObservationsEnvelope.model_validate(
        {
            **FRED_DGS10_RESPONSE,
            "observations": [
                {
                    "realtime_start": "2026-07-28",
                    "realtime_end": "2026-07-28",
                    "date": "2025-01-03",
                    "value": "4.60",
                },
                {
                    "realtime_start": "2026-07-28",
                    "realtime_end": "2026-07-28",
                    "date": "2025-01-01",
                    "value": ".",
                },
                {
                    "realtime_start": "2026-07-28",
                    "realtime_end": "2026-07-28",
                    "date": "2025-01-02",
                    "value": "4.56",
                },
            ],
        }
    )

    observations = parse_fred_observations(TreasurySeries.US_10Y, envelope)

    # 휴장일(".")은 빠지고, 실제로 값이 있는 첫 날짜부터 오름차순으로 담긴다.
    assert [item.observation_date for item in observations] == [date(2025, 1, 2), date(2025, 1, 3)]
    assert observations[0].yield_pct == Decimal("4.56")


def test_parse_fred_observations_returns_empty_when_all_missing() -> None:
    envelope = FredObservationsEnvelope.model_validate(
        {
            **FRED_DGS10_RESPONSE,
            "observations": [
                {
                    "realtime_start": "2026-07-28",
                    "realtime_end": "2026-07-28",
                    "date": "2025-01-01",
                    "value": ".",
                }
            ],
        }
    )

    assert parse_fred_observations(TreasurySeries.US_10Y, envelope) == ()

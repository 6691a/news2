import json

import pytest

from tests.kis.korea.fixtures import (
    SK_HYNIX_ORDERBOOK_FRAMES,
    SK_HYNIX_TRADE_FRAMES,
    SUBSCRIBE_SUCCESS_ORDERBOOK,
    SUBSCRIBE_SUCCESS_TRADE,
)


def split_frame(frame: str) -> tuple[str, str, str, list[str]]:
    """KIS 원본 프레임을 헤더와 body 필드로 분리한다."""

    data_type, tr_id, record_count, body = frame.split("|", 3)
    return data_type, tr_id, record_count, body.split("^")


@pytest.mark.parametrize(
    ("message", "expected_tr_id"),
    [
        (SUBSCRIBE_SUCCESS_ORDERBOOK, "H0STASP0"),
        (SUBSCRIBE_SUCCESS_TRADE, "H0STCNT0"),
    ],
)
def test_subscription_success_fixtures_are_valid_json(
    message: str,
    expected_tr_id: str,
) -> None:
    payload = json.loads(message)

    assert payload["header"] == {
        "tr_id": expected_tr_id,
        "tr_key": "000660",
        "encrypt": "N",
    }
    assert payload["body"]["rt_cd"] == "0"
    assert payload["body"]["msg1"] == "SUBSCRIBE SUCCESS"


def test_fixture_lists_have_three_frames_each() -> None:
    assert len(SK_HYNIX_ORDERBOOK_FRAMES) == 3
    assert len(SK_HYNIX_TRADE_FRAMES) == 3


@pytest.mark.parametrize("frame", SK_HYNIX_ORDERBOOK_FRAMES)
def test_orderbook_frame_structure_and_totals(frame: str) -> None:
    data_type, tr_id, record_count, fields = split_frame(frame)

    assert (data_type, tr_id, record_count) == ("0", "H0STASP0", "001")
    assert len(fields) == 62
    assert fields[0] == "000660"

    ask_quantities = [int(value) for value in fields[23:33]]
    bid_quantities = [int(value) for value in fields[33:43]]
    assert int(fields[43]) == sum(ask_quantities)
    assert int(fields[44]) == sum(bid_quantities)


@pytest.mark.parametrize("frame", SK_HYNIX_TRADE_FRAMES)
def test_trade_frame_structure(frame: str) -> None:
    data_type, tr_id, record_count, fields = split_frame(frame)

    assert (data_type, tr_id, record_count) == ("0", "H0STCNT0", "001")
    assert len(fields) == 46
    assert fields[0] == "000660"
    assert fields[1] == "103925"
    assert fields[2] == "1996000"


def test_trade_frames_preserve_first_three_actual_records() -> None:
    volume_pairs = []
    for frame in SK_HYNIX_TRADE_FRAMES:
        fields = split_frame(frame)[3]
        volume_pairs.append((int(fields[12]), int(fields[13])))

    assert volume_pairs == [
        (20, 2388396),
        (6, 2388402),
        (1, 2388403),
    ]

from datetime import date, time

from app.kis.schemas.parsing import none_if_empty, parse_kis_date, parse_kis_time


def test_parse_kis_date_converts_yyyymmdd() -> None:
    assert parse_kis_date("20260713") == date(2026, 7, 13)


def test_parse_kis_time_converts_hhmmss() -> None:
    assert parse_kis_time("103925") == time(10, 39, 25)


def test_none_if_empty_normalizes_only_empty_string() -> None:
    assert none_if_empty("") is None
    assert none_if_empty("0") == "0"

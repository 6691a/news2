import logging

import pytest

from app.core.logging import RedactUrlQuery


FRED_URL = "https://api.stlouisfed.org/fred/series/observations?series_id=DGS10&api_key=secret&file_type=json"


def _record(*args: object) -> logging.LogRecord:
    """httpx가 남기는 것과 같은 모양의 로그 레코드를 만든다."""

    return logging.LogRecord(
        name="httpx",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='HTTP Request: %s %s "%s %d %s"',
        args=args,
        exc_info=None,
    )


def test_url_query_is_removed_from_log_arguments() -> None:
    record = _record("GET", FRED_URL, "HTTP/1.1", 200, "OK")

    assert RedactUrlQuery().filter(record) is True
    # host와 path는 남아야 요청 대상을 계속 추적할 수 있다.
    assert record.args == ("GET", "https://api.stlouisfed.org/fred/series/observations", "HTTP/1.1", 200, "OK")
    assert "api_key" not in record.getMessage()


def test_record_is_never_dropped() -> None:
    record = _record("GET", "https://rest.example/uapi/quotations", "HTTP/1.1", 200, "OK")

    # 비밀값이 없어도 레코드를 버리지 않는다. 호출 실패와 무응답이 구분돼야 한다.
    assert RedactUrlQuery().filter(record) is True
    assert record.args == ("GET", "https://rest.example/uapi/quotations", "HTTP/1.1", 200, "OK")


@pytest.mark.parametrize(
    "value",
    [
        "not a url?with=query",
        "ftp://example.test/file?token=secret",
        42,
    ],
)
def test_non_http_arguments_are_left_alone(value: object) -> None:
    record = _record(value)

    RedactUrlQuery().filter(record)

    assert record.args == (value,)


def test_arguments_without_query_are_left_alone() -> None:
    record = _record("https://api.stlouisfed.org/fred/series/observations")

    RedactUrlQuery().filter(record)

    assert record.args == ("https://api.stlouisfed.org/fred/series/observations",)

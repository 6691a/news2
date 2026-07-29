"""외부 HTTP 응답 상태를 구조화 로그로 남기고 예외로 올리는 공용 도구."""

import httpx

from app.core.logging import get_logger


logger = get_logger(__name__)

# 본문 전체를 남기면 로그가 비대해진다. 원인 파악에 필요한 앞부분만 남긴다.
ERROR_BODY_LIMIT = 300


def log_http_error(
    *,
    status_code: int,
    method: str,
    host: str,
    path: str,
    text: str,
    **context: object,
) -> None:
    """외부 HTTP 4xx·5xx 응답을 구조화 ERROR 로그(`http_error_response`)로 남긴다.

    이벤트 이름과 필드명은 운영 알림 규칙이 참조하므로 고정이다. 본문 절단도 이
    함수 안에서 하므로 호출자는 원본 본문을 그대로 넘긴다.

    Args:
        status_code: 응답 상태 코드.
        method: 요청 HTTP 메서드.
        host: 요청 대상 host. 쿼리에 API 키가 실릴 수 있어 전체 URL은 받지 않는다.
        path: 요청 대상 path.
        text: 응답 본문 원본. 앞 `ERROR_BODY_LIMIT` 글자만 남긴다.
        **context: 로그에 함께 남길 호출 맥락(예: `series="US10Y"`).
    """

    logger.error(
        "http_error_response",
        status_code=status_code,
        method=method,
        host=host,
        path=path,
        body=text[:ERROR_BODY_LIMIT],
        **context,
    )


def raise_for_status(response: httpx.Response, **context: object) -> None:
    """4xx·5xx 응답이면 구조화 로그를 남기고 `httpx.HTTPStatusError`를 올린다.

    `response.raise_for_status()`를 직접 부르면 예외는 올라가지만 상태 코드가
    구조화 필드로 남지 않아 운영에서 `429`·`500` 같은 사건을 집계·알림할 수 없다.
    외부 API를 호출하는 모든 지점은 이 함수를 대신 쓴다.

    쿼리 문자열에는 API 키가 실릴 수 있어(FRED `api_key`) host와 path만 남긴다.

    Args:
        response: 검사할 HTTP 응답.
        **context: 로그에 함께 남길 호출 맥락(예: `series="US10Y"`).

    Raises:
        httpx.HTTPStatusError: 응답 상태가 4xx 또는 5xx인 경우.
    """

    if not response.is_error:
        return

    log_http_error(
        status_code=response.status_code,
        method=response.request.method,
        host=response.request.url.host,
        path=response.request.url.path,
        text=response.text,
        **context,
    )
    response.raise_for_status()

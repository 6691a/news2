"""Sentry 오류 추적 초기화와 전송 전 민감정보 제거."""

from collections.abc import Mapping
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.fastapi import FastApiIntegration

from app.core.config import Settings


FILTERED = "[Filtered]"
SECRET_KEYS = frozenset(
    {
        "api_key",
        "app_key",
        "app_secret",
        "authorization",
        "cookie",
        "database_url",
        "dsn",
        "openai_api_key",
        "password",
        "redis_url",
        "sentry_dsn",
        "slack_bot_token",
        "token",
    }
)


def _is_secret_key(key: object) -> bool:
    normalized = str(key).casefold().replace("-", "_")
    return normalized in SECRET_KEYS or normalized.endswith(("_key", "_secret", "_token", "_password"))


def _scrub_url(value: str) -> str:
    try:
        parts = urlsplit(value)
    except ValueError:
        return value
    if not parts.scheme or not parts.netloc or not parts.query:
        return value
    query = [(key, FILTERED if _is_secret_key(key) else item) for key, item in parse_qsl(parts.query)]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _scrub_value(value: object, *, key: object | None = None) -> object:
    if key is not None and _is_secret_key(key):
        return FILTERED
    if isinstance(value, Mapping):
        return {item_key: _scrub_value(item, key=item_key) for item_key, item in value.items()}
    if isinstance(value, list):
        return [_scrub_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_scrub_value(item) for item in value)
    if isinstance(value, str):
        return _scrub_url(value)
    return value


def scrub_sentry_event(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
    """Sentry 이벤트에서 자격 증명과 연결 문자열을 제거한다.

    Args:
        event: Sentry가 전송하려는 이벤트.
        hint: Sentry SDK가 제공하는 원본 예외 문맥.

    Returns:
        제자리에서 정제된 이벤트.
    """

    del hint
    scrubbed = _scrub_value(event)
    assert isinstance(scrubbed, dict)
    event.clear()
    event.update(scrubbed)
    return event


def configure_sentry(settings: Settings) -> None:
    """DSN이 설정된 프로세스에서 Sentry 오류 추적을 초기화한다.

    Args:
        settings: Sentry 환경과 release를 포함한 애플리케이션 설정.
    """

    if not settings.sentry_dsn:
        return
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment,
        release=settings.sentry_release or None,
        send_default_pii=False,
        before_send=scrub_sentry_event,
        integrations=[CeleryIntegration(), FastApiIntegration()],
    )

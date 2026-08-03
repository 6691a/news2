"""Sentry 오류 추적과 전송 전 민감정보 제거를 구성한다."""

from collections.abc import Mapping
from enum import StrEnum
import logging
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import sentry_sdk
from sentry_sdk.integrations.asyncio import AsyncioIntegration
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.scrubber import EventScrubber

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
        "fred_api_key",
        "kis_app_key",
        "kis_app_secret",
        "openai_api_key",
        "password",
        "redis_url",
        "sentry_dsn",
        "slack_bot_token",
        "token",
    }
)


class SentryRuntime(StrEnum):
    """Sentry 이벤트를 발생시킨 프로세스 실행 환경."""

    FASTAPI = "fastapi"
    CELERY = "celery"
    CELERY_WORKER = "celery-worker"
    CELERY_BEAT = "celery-beat"
    SCRIPT = "script"


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


def _event_scrubber() -> EventScrubber:
    """프로젝트 인증정보를 재귀적으로 마스킹하는 scrubber를 만든다."""

    return EventScrubber(
        denylist=list(SECRET_KEYS),
        recursive=True,
        send_default_pii=False,
    )


def configure_sentry(settings: Settings, runtime: SentryRuntime = SentryRuntime.SCRIPT) -> None:
    """공통 SDK 옵션과 프로세스 태그로 Sentry를 초기화한다.

    Args:
        settings: 검증을 마친 애플리케이션 및 Sentry 설정.
        runtime: 현재 프로세스의 실행 환경.
    """

    if not settings.sentry_dsn:
        return
    sentry_sdk.init(
        dsn=str(settings.sentry_dsn),
        environment=settings.sentry_environment,
        release=settings.sentry_release or None,
        sample_rate=settings.sentry_error_sample_rate,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=False,
        before_send=scrub_sentry_event,
        event_scrubber=_event_scrubber(),
        integrations=[
            AsyncioIntegration(),
            FastApiIntegration(),
            CeleryIntegration(),
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
    )
    scope = sentry_sdk.get_global_scope()
    scope.set_tag("service", "news2")
    scope.set_tag("runtime", runtime.value)


def set_sentry_runtime(runtime: SentryRuntime) -> None:
    """현재 프로세스의 Sentry 실행 환경 태그를 변경한다.

    Args:
        runtime: 새로 확인된 프로세스 실행 환경.
    """

    sentry_sdk.get_global_scope().set_tag("runtime", runtime.value)


def flush_sentry(timeout: float = 2.0) -> None:
    """제한 시간 동안 전송 대기 중인 Sentry 이벤트를 보낸다.

    Args:
        timeout: 전송 완료를 기다릴 최대 시간(초).
    """

    sentry_sdk.flush(timeout=timeout)

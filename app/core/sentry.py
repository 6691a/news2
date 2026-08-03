'''Sentry 오류 및 성능 모니터링을 모든 애플리케이션 실행 환경에 구성한다.'''

from enum import StrEnum
import logging

import sentry_sdk
from sentry_sdk.integrations.asyncio import AsyncioIntegration
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.scrubber import EventScrubber

from app.core.config import Settings


_PROJECT_SECRET_FIELDS = [
    'authorization',
    'cookie',
    'dsn',
    'fred_api_key',
    'kis_app_key',
    'kis_app_secret',
    'password',
    'token',
]


class SentryRuntime(StrEnum):
    '''Sentry 이벤트를 발생시킨 프로세스 실행 환경.'''

    FASTAPI = 'fastapi'
    CELERY = 'celery'
    CELERY_WORKER = 'celery-worker'
    CELERY_BEAT = 'celery-beat'
    SCRIPT = 'script'


def configure_sentry(settings: Settings, runtime: SentryRuntime) -> None:
    '''공통 SDK 옵션과 프로세스 태그로 Sentry를 초기화한다.

    Args:
        settings: 검증을 마친 애플리케이션 및 Sentry 설정.
        runtime: 현재 프로세스의 실행 환경.
    '''

    sentry_sdk.init(
        dsn=str(settings.sentry_dsn),
        environment=settings.sentry_environment,
        release=settings.sentry_release,
        sample_rate=settings.sentry_error_sample_rate,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=False,
        event_scrubber=_event_scrubber(),
        integrations=[
            AsyncioIntegration(),
            FastApiIntegration(),
            CeleryIntegration(),
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
    )
    scope = sentry_sdk.get_global_scope()
    scope.set_tag('service', 'news2')
    scope.set_tag('runtime', runtime.value)


def set_sentry_runtime(runtime: SentryRuntime) -> None:
    '''현재 프로세스의 Sentry 실행 환경 태그를 변경한다.

    Args:
        runtime: 새로 확인된 프로세스 실행 환경.
    '''

    sentry_sdk.get_global_scope().set_tag('runtime', runtime.value)


def flush_sentry(timeout: float = 2.0) -> None:
    '''제한 시간 동안 전송 대기 중인 Sentry 이벤트를 보낸다.

    Args:
        timeout: 전송 완료를 기다릴 최대 시간(초).
    '''

    sentry_sdk.flush(timeout=timeout)


def _event_scrubber() -> EventScrubber:
    '''프로젝트 인증정보를 재귀적으로 마스킹하는 scrubber를 만든다.'''

    return EventScrubber(
        denylist=_PROJECT_SECRET_FIELDS,
        recursive=True,
        send_default_pii=False,
    )

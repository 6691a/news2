from collections.abc import Callable
import logging

import pytest
import sentry_sdk
from sentry_sdk.envelope import Envelope
from sentry_sdk.integrations.asyncio import AsyncioIntegration
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.transport import Transport

from app.core.config import Settings
from app.core.sentry import SentryRuntime, configure_sentry, flush_sentry, set_sentry_runtime


class CapturingTransport(Transport):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[dict[str, object]] = []

    def capture_envelope(self, envelope: Envelope) -> None:
        for item in envelope.items:
            event = item.get_event()
            if event is not None:
                self.events.append(event)


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        database_url='postgresql+asyncpg://user:pass@localhost/news2',
        redis_url='redis://localhost:6379/0',
        kis_app_key='app-key',
        kis_app_secret='app-secret',
        kis_rest_domain='https://rest.example',
        kis_websocket_domain='wss://websocket.example',
        kis_virtual_rest_domain='https://virtual-rest.example',
        kis_virtual_websocket_domain='wss://virtual-websocket.example',
        fred_api_key='fred-key',
        sentry_dsn='https://public@example.ingest.sentry.io/1',
        sentry_environment='test',
        sentry_release='news2@test',
        sentry_traces_sample_rate=0.0,
        sentry_error_sample_rate=1.0,
    )


def test_configure_sentry_captures_tagged_scrubbed_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = CapturingTransport()
    real_init: Callable[..., object] = sentry_sdk.init
    monkeypatch.setattr(
        sentry_sdk,
        'init',
        lambda *args, **kwargs: real_init(*args, transport=transport, **kwargs),
    )

    try:
        configure_sentry(_settings(), SentryRuntime.SCRIPT)
        client = sentry_sdk.get_client()
        assert client.options['environment'] == 'test'
        assert client.options['release'] == 'news2@test'
        assert client.options['sample_rate'] == 1.0
        assert client.options['traces_sample_rate'] == 0.0
        assert client.options['send_default_pii'] is False
        assert client.get_integration(AsyncioIntegration) is not None
        assert client.get_integration(FastApiIntegration) is not None
        assert client.get_integration(CeleryIntegration) is not None
        assert client.get_integration(LoggingIntegration) is not None

        with sentry_sdk.new_scope() as scope:
            scope.set_extra('kis_app_secret', 'secret')
            scope.set_extra('nested', {'fred_api_key': 'fred', 'authorization': 'Bearer token'})
            sentry_sdk.capture_exception(RuntimeError('boom'))

        set_sentry_runtime(SentryRuntime.CELERY_BEAT)
        sentry_sdk.capture_message('beat is alive', level=logging.ERROR)
        flush_sentry()
    finally:
        sentry_sdk.get_client().close()

    assert len(transport.events) == 2
    exception_event, message_event = transport.events
    assert exception_event['tags']['service'] == 'news2'
    assert exception_event['tags']['runtime'] == 'script'
    assert exception_event['extra']['kis_app_secret'] == '[Filtered]'
    assert exception_event['extra']['nested']['fred_api_key'] == '[Filtered]'
    assert exception_event['extra']['nested']['authorization'] == '[Filtered]'
    assert message_event['tags']['runtime'] == 'celery-beat'

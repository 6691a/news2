from collections.abc import Callable
import logging
from unittest.mock import Mock

import pytest
import sentry_sdk
from sentry_sdk.envelope import Envelope
from sentry_sdk.integrations.asyncio import AsyncioIntegration
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.transport import Transport

from app.core.config import Settings
from app.core.sentry import (
    SentryRuntime,
    configure_sentry,
    flush_sentry,
    scrub_sentry_event,
    set_sentry_runtime,
)
from tests.core.test_config import build_settings


class CapturingTransport(Transport):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[dict[str, object]] = []

    def capture_envelope(self, envelope: Envelope) -> None:
        for item in envelope.items:
            event = item.get_event()
            if event is not None:
                self.events.append(event)


def test_configure_sentry_skips_empty_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    init = Mock()
    monkeypatch.setattr("app.core.sentry.sentry_sdk.init", init)

    configure_sentry(build_settings(sentry_dsn=""))

    init.assert_not_called()


def test_configure_sentry_uses_environment_release_and_scrubber(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init = Mock()
    monkeypatch.setattr("app.core.sentry.sentry_sdk.init", init)
    settings: Settings = build_settings(
        sentry_dsn="https://public@example.ingest.sentry.io/1",
        sentry_environment="test",
        sentry_release="news2@1.2.3",
    )

    configure_sentry(settings, SentryRuntime.FASTAPI)

    kwargs = init.call_args.kwargs
    assert kwargs["dsn"] == str(settings.sentry_dsn)
    assert kwargs["environment"] == "test"
    assert kwargs["release"] == "news2@1.2.3"
    assert kwargs["sample_rate"] == 1.0
    assert kwargs["traces_sample_rate"] == 0.1
    assert kwargs["send_default_pii"] is False
    assert kwargs["before_send"] is scrub_sentry_event
    assert {type(integration).__name__ for integration in kwargs["integrations"]} == {
        "AsyncioIntegration",
        "CeleryIntegration",
        "FastApiIntegration",
        "LoggingIntegration",
    }


def test_configure_sentry_captures_tagged_scrubbed_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = CapturingTransport()
    real_init: Callable[..., object] = sentry_sdk.init
    monkeypatch.setattr(
        sentry_sdk,
        "init",
        lambda *args, **kwargs: real_init(*args, transport=transport, **kwargs),
    )

    try:
        configure_sentry(
            build_settings(
                sentry_dsn="https://public@example.ingest.sentry.io/1",
                sentry_environment="test",
                sentry_release="news2@test",
                sentry_traces_sample_rate=0.0,
                sentry_error_sample_rate=1.0,
            ),
            SentryRuntime.SCRIPT,
        )
        client = sentry_sdk.get_client()
        assert client.get_integration(AsyncioIntegration) is not None
        assert client.get_integration(FastApiIntegration) is not None
        assert client.get_integration(CeleryIntegration) is not None
        assert client.get_integration(LoggingIntegration) is not None

        with sentry_sdk.new_scope() as scope:
            scope.set_extra("kis_app_secret", "secret")
            scope.set_extra("nested", {"fred_api_key": "fred", "authorization": "Bearer token"})
            sentry_sdk.capture_exception(RuntimeError("boom"))

        set_sentry_runtime(SentryRuntime.CELERY_BEAT)
        sentry_sdk.capture_message("beat is alive", level=logging.ERROR)
        flush_sentry()
    finally:
        sentry_sdk.get_client().close()

    assert len(transport.events) == 2
    exception_event, message_event = transport.events
    assert exception_event["tags"]["service"] == "news2"
    assert exception_event["tags"]["runtime"] == "script"
    assert exception_event["extra"]["kis_app_secret"] == "[Filtered]"
    assert exception_event["extra"]["nested"]["fred_api_key"] == "[Filtered]"
    assert exception_event["extra"]["nested"]["authorization"] == "[Filtered]"
    assert message_event["tags"]["runtime"] == "celery-beat"


def test_scrub_sentry_event_removes_nested_secrets() -> None:
    event = {
        "request": {
            "headers": {
                "Authorization": "Bearer secret",
                "Cookie": "session=secret",
                "Accept": "application/json",
            },
            "url": "https://api.example.com/data?api_key=secret&series=US10Y",
        },
        "extra": {
            "api_key": "secret",
            "database_url": "postgresql://user:password@localhost/news2",
            "series": "US10Y",
        },
    }

    scrubbed = scrub_sentry_event(event, {})

    assert scrubbed is event
    assert event["request"]["headers"]["Authorization"] == "[Filtered]"
    assert event["request"]["headers"]["Cookie"] == "[Filtered]"
    assert event["request"]["headers"]["Accept"] == "application/json"
    assert event["request"]["url"] == "https://api.example.com/data?api_key=%5BFiltered%5D&series=US10Y"
    assert event["extra"]["api_key"] == "[Filtered]"
    assert event["extra"]["database_url"] == "[Filtered]"
    assert event["extra"]["series"] == "US10Y"

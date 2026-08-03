from unittest.mock import Mock

import pytest

from app.core.config import Settings
from app.core.sentry import configure_sentry, scrub_sentry_event
from tests.core.test_config import build_settings


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

    configure_sentry(settings)

    kwargs = init.call_args.kwargs
    assert kwargs["dsn"] == settings.sentry_dsn
    assert kwargs["environment"] == "test"
    assert kwargs["release"] == "news2@1.2.3"
    assert kwargs["send_default_pii"] is False
    assert kwargs["before_send"] is scrub_sentry_event
    assert {type(integration).__name__ for integration in kwargs["integrations"]} == {
        "CeleryIntegration",
        "FastApiIntegration",
    }


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

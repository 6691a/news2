from collections.abc import Mapping

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def build_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "database_url": "postgresql+asyncpg://news2:news2@localhost/news2",
        "redis_url": "redis://localhost:6379/0",
        "kis_app_key": "app-key",
        "kis_app_secret": "app-secret",
        "kis_rest_domain": "https://kis.example.com",
        "kis_websocket_domain": "wss://kis.example.com",
        "kis_virtual_rest_domain": "https://virtual-kis.example.com",
        "kis_virtual_websocket_domain": "wss://virtual-kis.example.com",
        "fred_api_key": "fred-key",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


def test_notification_settings_default_to_safe_local_values() -> None:
    settings = build_settings()

    assert settings.sentry_dsn == ""
    assert settings.sentry_environment == "local"
    assert settings.slack_notifications_enabled is False
    assert settings.issue_digest_interval_seconds == 3600
    assert settings.issue_event_retention_seconds == 86400
    assert settings.issue_llm_provider == "openai"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"slack_bot_token": ""}, "SLACK_BOT_TOKEN"),
        ({"slack_issues_channel_id": ""}, "SLACK_ISSUES_CHANNEL_ID"),
        ({"slack_reports_channel_id": ""}, "SLACK_REPORTS_CHANNEL_ID"),
        ({"issue_llm_model": ""}, "ISSUE_LLM_MODEL"),
        ({"openai_api_key": ""}, "OPENAI_API_KEY"),
    ],
)
def test_enabled_slack_requires_delivery_and_llm_settings(
    overrides: Mapping[str, object],
    message: str,
) -> None:
    enabled = {
        "slack_notifications_enabled": True,
        "slack_bot_token": "xoxb-test",
        "slack_issues_channel_id": "CISSUES",
        "slack_reports_channel_id": "CREPORTS",
        "issue_llm_model": "gpt-test",
        "openai_api_key": "sk-test",
    }
    enabled.update(overrides)

    with pytest.raises(ValidationError, match=message):
        build_settings(**enabled)


def test_issue_event_retention_covers_two_digest_intervals() -> None:
    with pytest.raises(ValidationError, match="ISSUE_EVENT_RETENTION_SECONDS"):
        build_settings(
            issue_digest_interval_seconds=50_000,
            issue_event_retention_seconds=86_400,
        )


def test_unsupported_llm_provider_is_rejected() -> None:
    with pytest.raises(ValidationError, match="ISSUE_LLM_PROVIDER"):
        build_settings(issue_llm_provider="unknown")

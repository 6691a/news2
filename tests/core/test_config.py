from collections.abc import Iterator

from pydantic import ValidationError
import pytest

from app.core.config import Settings


@pytest.fixture
def required_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, object]]:
    for name in (
        'SENTRY_DSN',
        'SENTRY_ENVIRONMENT',
        'SENTRY_RELEASE',
        'SENTRY_TRACES_SAMPLE_RATE',
        'SENTRY_ERROR_SAMPLE_RATE',
    ):
        monkeypatch.delenv(name, raising=False)
    yield {
        'database_url': 'postgresql+asyncpg://user:pass@localhost/news2',
        'redis_url': 'redis://localhost:6379/0',
        'kis_app_key': 'app-key',
        'kis_app_secret': 'app-secret',
        'kis_rest_domain': 'https://rest.example',
        'kis_websocket_domain': 'wss://websocket.example',
        'kis_virtual_rest_domain': 'https://virtual-rest.example',
        'kis_virtual_websocket_domain': 'wss://virtual-websocket.example',
        'fred_api_key': 'fred-key',
        'sentry_dsn': 'https://public@example.ingest.sentry.io/1',
        'sentry_environment': 'test',
        'sentry_release': 'news2@test',
    }


@pytest.mark.parametrize('field', ['sentry_dsn', 'sentry_environment', 'sentry_release'])
def test_sentry_required_setting_cannot_be_missing(
    required_settings: dict[str, object],
    field: str,
) -> None:
    required_settings.pop(field)

    with pytest.raises(ValidationError):
        Settings(_env_file=None, **required_settings)


@pytest.mark.parametrize('field', ['sentry_dsn', 'sentry_environment', 'sentry_release'])
def test_sentry_required_setting_cannot_be_blank(
    required_settings: dict[str, object],
    field: str,
) -> None:
    required_settings[field] = '   '

    with pytest.raises(ValidationError):
        Settings(_env_file=None, **required_settings)


def test_sentry_dsn_requires_https(required_settings: dict[str, object]) -> None:
    required_settings['sentry_dsn'] = 'http://public@example.ingest.sentry.io/1'

    with pytest.raises(ValidationError):
        Settings(_env_file=None, **required_settings)


@pytest.mark.parametrize('field', ['sentry_traces_sample_rate', 'sentry_error_sample_rate'])
@pytest.mark.parametrize('value', [-0.01, 1.01, ''])
def test_sentry_sample_rate_must_be_between_zero_and_one(
    required_settings: dict[str, object],
    field: str,
    value: object,
) -> None:
    required_settings[field] = value

    with pytest.raises(ValidationError):
        Settings(_env_file=None, **required_settings)


def test_sentry_sample_rates_have_safe_defaults(required_settings: dict[str, object]) -> None:
    settings = Settings(_env_file=None, **required_settings)

    assert settings.sentry_traces_sample_rate == 0.1
    assert settings.sentry_error_sample_rate == 1.0

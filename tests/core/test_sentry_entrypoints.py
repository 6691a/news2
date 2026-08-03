import importlib
import sys
from unittest.mock import Mock

import pytest

import app.core.sentry as sentry_module


@pytest.mark.parametrize(
    ("module_name", "runtime"),
    [
        ("app.main", sentry_module.SentryRuntime.FASTAPI),
        ("app.core.celery", sentry_module.SentryRuntime.CELERY),
    ],
)
def test_process_entrypoint_configures_sentry(
    monkeypatch: pytest.MonkeyPatch,
    module_name: str,
    runtime: sentry_module.SentryRuntime,
) -> None:
    configure = Mock()
    monkeypatch.setattr(sentry_module, "configure_sentry", configure)
    sys.modules.pop(module_name, None)

    imported = importlib.import_module(module_name)

    settings = imported.container.settings() if module_name == "app.main" else imported.settings
    configure.assert_called_once_with(settings, runtime)

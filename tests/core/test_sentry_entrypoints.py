import importlib
import sys
from unittest.mock import Mock

import pytest

import app.core.sentry as sentry_module


@pytest.mark.parametrize("module_name", ["app.main", "app.core.celery"])
def test_process_entrypoint_configures_sentry(
    monkeypatch: pytest.MonkeyPatch,
    module_name: str,
) -> None:
    configure = Mock()
    monkeypatch.setattr(sentry_module, "configure_sentry", configure)
    sys.modules.pop(module_name, None)

    imported = importlib.import_module(module_name)

    configure.assert_called_once_with(imported.container.settings() if module_name == "app.main" else imported.settings)

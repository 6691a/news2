import importlib
from unittest.mock import patch

from app.core.containers import container
from app.core.sentry import SentryRuntime


def test_fastapi_module_configures_sentry_before_serving() -> None:
    main_module = importlib.import_module('app.main')

    with patch('app.core.sentry.configure_sentry') as configure:
        importlib.reload(main_module)

    configure.assert_called_once_with(container.settings(), SentryRuntime.FASTAPI)

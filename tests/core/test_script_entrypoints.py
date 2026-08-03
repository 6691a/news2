import asyncio
import importlib
import runpy
import sys
from unittest.mock import patch

import pytest

from app.core.containers import container
from app.core.sentry import SentryRuntime


SCRIPT_MODULES = (
    'app.ohlcv.__main__',
    'app.kis.korea.__main__',
    'app.kis.overseas.__main__',
    'app.kis.korea.investor.__main__',
    'app.macro.us.treasury.__main__',
)


@pytest.mark.parametrize('module_name', SCRIPT_MODULES)
def test_script_module_configures_sentry(module_name: str) -> None:
    module = importlib.import_module(module_name)

    with patch('app.core.sentry.configure_sentry') as configure:
        importlib.reload(module)

    configure.assert_called_once_with(container.settings(), SentryRuntime.SCRIPT)


@pytest.mark.parametrize('module_name', SCRIPT_MODULES)
def test_script_module_flushes_sentry_on_shutdown(
    module_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, 'argv', [module_name])
    monkeypatch.delitem(sys.modules, module_name, raising=False)

    with (
        patch('app.core.sentry.flush_sentry') as flush,
        patch.object(asyncio, 'run') as run,
    ):
        run.side_effect = lambda coroutine: coroutine.close()
        runpy.run_module(module_name, run_name='__main__', alter_sys=True)

    flush.assert_called_once_with()

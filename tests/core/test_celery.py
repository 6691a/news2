from unittest.mock import patch

from app.core.celery import _set_beat_runtime, _set_worker_runtime
from app.core.sentry import SentryRuntime


def test_worker_signal_sets_worker_runtime() -> None:
    with patch('app.core.celery.set_sentry_runtime') as set_runtime:
        _set_worker_runtime()

    set_runtime.assert_called_once_with(SentryRuntime.CELERY_WORKER)


def test_beat_signal_sets_beat_runtime() -> None:
    with patch('app.core.celery.set_sentry_runtime') as set_runtime:
        _set_beat_runtime()

    set_runtime.assert_called_once_with(SentryRuntime.CELERY_BEAT)

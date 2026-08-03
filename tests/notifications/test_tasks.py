from dependency_injector import providers
from types import SimpleNamespace

from app.core.containers import container
from app.notifications.models import IssueEvent, IssueKind
from app.notifications.tasks import record_task_retry_issue, task_send_issue_digests


class FakeDigestService:
    def __init__(self) -> None:
        self.calls = 0

    async def run(self) -> int:
        self.calls += 1
        return 2


def test_celery_task_runs_injected_digest_service() -> None:
    service = FakeDigestService()

    with container.issue_digest_service.override(providers.Object(service)):
        result = task_send_issue_digests.run()

    assert result == 2
    assert service.calls == 1


class RecordingCollector:
    def __init__(self, *, failure: BaseException | None = None) -> None:
        self.failure = failure
        self.events: list[IssueEvent] = []

    async def record(self, event: IssueEvent) -> bool:
        self.events.append(event)
        if self.failure:
            raise self.failure
        return True


def test_retry_signal_records_structured_issue_without_exception_text() -> None:
    collector = RecordingCollector()
    request = SimpleNamespace(
        task="ohlcv.collect_overseas_daily",
        retries=2,
        id="task-123",
    )

    with container.issue_collector.override(providers.Object(collector)):
        record_task_retry_issue(
            request=request,
            reason=ValueError("secret token=do-not-record"),
            einfo=None,
        )

    assert len(collector.events) == 1
    event = collector.events[0]
    assert event.kind is IssueKind.RETRY_SCHEDULED
    assert event.operation == "ohlcv.collect_overseas_daily"
    assert event.correlation_id == "task-123"
    assert event.context == {"retry_count": 2, "reason_type": "ValueError"}
    assert "do-not-record" not in event.model_dump_json()


def test_retry_signal_failure_does_not_change_retry_flow() -> None:
    collector = RecordingCollector(failure=RuntimeError("redis unavailable"))
    request = SimpleNamespace(task="example.task", retries=1, id="task-456")

    with container.issue_collector.override(providers.Object(collector)):
        record_task_retry_issue(request=request, reason=TimeoutError(), einfo=None)

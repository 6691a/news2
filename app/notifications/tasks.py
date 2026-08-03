"""Slack 운영 이슈 digest Celery 작업."""

import asyncio

import sentry_sdk
from celery.signals import task_retry

from app.core.celery import app
from app.core.containers import container
from app.core.logging import get_logger
from app.notifications.models import IssueEvent, IssueKind


logger = get_logger(__name__)


@app.task(name="notifications.send_issue_digests")
def task_send_issue_digests() -> int:
    """완료된 이슈 버킷을 분석해 Slack으로 전송한다."""

    return asyncio.run(container.issue_digest_service().run())


@task_retry.connect
def record_task_retry_issue(
    sender: object | None = None,
    request: object | None = None,
    reason: object | None = None,
    einfo: object | None = None,
    **_: object,
) -> None:
    """Celery 중간 재시도를 민감한 예외 본문 없이 IssueEvent로 기록한다."""

    del sender, einfo
    task_name = str(getattr(request, "task", "unknown") or "unknown")
    task_id = str(getattr(request, "id", "") or "") or None
    retry_count = int(getattr(request, "retries", 0) or 0)
    reason_type = type(reason).__name__ if reason is not None else "unknown"
    event = IssueEvent.create(
        kind=IssueKind.RETRY_SCHEDULED,
        service="celery",
        operation=task_name,
        summary="Celery task retry scheduled.",
        correlation_id=task_id,
        context={"retry_count": retry_count, "reason_type": reason_type},
    )
    try:
        asyncio.run(container.issue_collector().record(event))
    except Exception as exc:
        logger.exception(
            "task_retry_issue_record_failed",
            operation=task_name,
            error_type=type(exc).__name__,
        )
        sentry_sdk.capture_exception(exc)

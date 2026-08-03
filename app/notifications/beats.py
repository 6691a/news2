"""Slack 운영 이슈 digest의 Celery beat 설정."""

from datetime import timedelta
from typing import Any, Protocol

from app.core.config import settings as app_settings


class NotificationScheduleSettings(Protocol):
    """Beat 구성에 필요한 설정의 최소 계약."""

    slack_notifications_enabled: bool
    issue_digest_interval_seconds: int


def beat_schedule(
    settings: NotificationScheduleSettings = app_settings,
) -> dict[str, dict[str, Any]]:
    """알림 활성화 시 완료 버킷 확인 작업을 최대 1분 간격으로 등록한다."""

    if not settings.slack_notifications_enabled:
        return {}
    poll_seconds = min(60, settings.issue_digest_interval_seconds)
    return {
        "notifications-issue-digest": {
            "task": "notifications.send_issue_digests",
            "schedule": timedelta(seconds=poll_seconds),
        }
    }

from types import SimpleNamespace

from app.notifications.beats import beat_schedule


def test_issue_digest_beat_is_disabled_with_notifications() -> None:
    config = SimpleNamespace(slack_notifications_enabled=False, issue_digest_interval_seconds=3600)

    assert beat_schedule(config) == {}  # type: ignore[arg-type]


def test_issue_digest_beat_checks_completed_buckets_at_most_every_minute() -> None:
    config = SimpleNamespace(slack_notifications_enabled=True, issue_digest_interval_seconds=3600)

    schedule = beat_schedule(config)  # type: ignore[arg-type]

    assert schedule["notifications-issue-digest"]["task"] == "notifications.send_issue_digests"
    assert schedule["notifications-issue-digest"]["schedule"].total_seconds() == 60


def test_celery_registers_notification_task_module() -> None:
    from app.core.celery import app

    assert "app.notifications.tasks" in app.conf.imports

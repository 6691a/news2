from datetime import UTC, datetime

import pytest

from app.notifications.aggregator import IssueAggregator, IssueBucket
from app.notifications.models import IssueEvent, IssueKind, IssueSeverity
from app.notifications.slack import SlackReceipt
from tests.notifications.fakes import FakeRedis


def event_json(*, minute: int, severity: IssueSeverity = IssueSeverity.WARNING) -> str:
    return IssueEvent.create(
        kind=IssueKind.RETRY_SCHEDULED,
        service="celery",
        operation="ohlcv.collect_overseas_daily",
        observed_at=datetime(2026, 8, 3, 4, minute, tzinfo=UTC),
        severity=severity,
        context={"retry_count": minute // 10 + 1},
    ).model_dump_json()


@pytest.mark.asyncio
async def test_pending_buckets_ignore_current_and_discover_previous_interval() -> None:
    redis = FakeRedis()
    old_key = "news2:notifications:issues:1800:1785727800:events"
    complete_key = "news2:notifications:issues:3600:1785729600:events"
    current_key = "news2:notifications:issues:3600:1785733200:events"
    redis.values[old_key] = [event_json(minute=0)]
    redis.values[complete_key] = [event_json(minute=10)]
    redis.values[current_key] = [event_json(minute=20)]
    aggregator = IssueAggregator(redis=redis, retention_seconds=86400)

    buckets = await aggregator.pending_buckets(datetime(2026, 8, 3, 5, 10, tzinfo=UTC))

    assert [bucket.events_key for bucket in buckets] == [old_key, complete_key]


@pytest.mark.asyncio
async def test_pending_buckets_skip_sent_bucket() -> None:
    redis = FakeRedis()
    key = "news2:notifications:issues:3600:1785729600:events"
    redis.values[key] = [event_json(minute=10)]
    redis.values[key.removesuffix(":events") + ":sent"] = '{"channel":"C","ts":"1"}'
    aggregator = IssueAggregator(redis=redis, retention_seconds=86400)

    buckets = await aggregator.pending_buckets(datetime(2026, 8, 3, 6, 0, tzinfo=UTC))

    assert buckets == []


@pytest.mark.asyncio
async def test_build_digest_groups_fingerprint_and_uses_highest_severity() -> None:
    redis = FakeRedis()
    key = "news2:notifications:issues:3600:1785729600:events"
    redis.values[key] = [event_json(minute=0), event_json(minute=30, severity=IssueSeverity.HIGH)]
    aggregator = IssueAggregator(redis=redis, retention_seconds=86400)
    bucket = IssueBucket.parse(key)

    digest = await aggregator.build_digest(bucket)

    assert digest.total_events == 2
    assert len(digest.groups) == 1
    assert digest.groups[0].severity is IssueSeverity.HIGH
    assert digest.groups[0].first_observed_at == datetime(2026, 8, 3, 4, 0, tzinfo=UTC)
    assert digest.groups[0].last_observed_at == datetime(2026, 8, 3, 4, 30, tzinfo=UTC)


@pytest.mark.asyncio
async def test_lock_and_sent_marker_prevent_duplicate_processing() -> None:
    redis = FakeRedis()
    key = "news2:notifications:issues:3600:1785729600:events"
    redis.values[key] = [event_json(minute=0)]
    aggregator = IssueAggregator(redis=redis, retention_seconds=86400)
    bucket = IssueBucket.parse(key)

    first_token = await aggregator.acquire(bucket)
    second_token = await aggregator.acquire(bucket)

    assert first_token is not None
    assert second_token is None
    await aggregator.release(bucket, first_token)
    await aggregator.mark_sent(bucket, SlackReceipt(channel="CISSUES", ts="123.456"))
    assert await redis.get(bucket.sent_key) == '{"channel":"CISSUES","ts":"123.456"}'

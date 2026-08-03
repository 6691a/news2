from datetime import UTC, datetime

import pytest

from app.notifications.collector import IssueCollector
from app.notifications.models import IssueEvent, IssueKind
from tests.notifications.fakes import FakeRedis


@pytest.mark.asyncio
async def test_collector_records_redacted_event_in_hour_bucket() -> None:
    redis = FakeRedis()
    collector = IssueCollector(redis=redis, interval_seconds=3600, retention_seconds=86400)
    event = IssueEvent.create(
        kind=IssueKind.RETRY_SCHEDULED,
        service="celery",
        operation="ohlcv.collect_overseas_daily",
        observed_at=datetime(2026, 8, 3, 4, 37, 10, tzinfo=UTC),
        context={"series": "AAPL", "reason_type": "HTTPError"},
    )

    recorded = await collector.record(event)

    key = "news2:notifications:issues:3600:1785729600:events"
    assert recorded is True
    assert key in redis.values
    assert redis.expiries[key] == 86400
    assert '"series":"AAPL"' in redis.values[key][0]


@pytest.mark.asyncio
async def test_collector_isolates_redis_failure() -> None:
    redis = FakeRedis()
    redis.fail_writes = True
    collector = IssueCollector(redis=redis, interval_seconds=3600, retention_seconds=86400)

    recorded = await collector.record(
        IssueEvent.create(kind=IssueKind.EMPTY_RESULT, service="ohlcv", operation="collect_korea")
    )

    assert recorded is False

from datetime import UTC, datetime

import pytest

from app.notifications.aggregator import IssueAggregator
from app.notifications.models import (
    AnalysisConfidence,
    AnalysisSource,
    IssueAnalysis,
    IssueDigest,
    IssueEvent,
    IssueKind,
)
from app.notifications.service import IssueDigestService
from app.notifications.slack import RenderedMessage, SlackDeliveryError, SlackReceipt
from tests.notifications.fakes import FakeRedis


class StaticAnalyzer:
    async def analyze(self, _: IssueDigest) -> IssueAnalysis:
        return IssueAnalysis(
            overview="재시도가 반복됐습니다.",
            likely_causes=[],
            impact="수집이 지연될 수 있습니다.",
            recommended_actions=["작업 로그를 확인하세요."],
            confidence=AnalysisConfidence.LOW,
            evidence=["재시도 1회"],
            generated_by=AnalysisSource.LLM,
        )


class RecordingSlackGateway:
    def __init__(self, *, failure: BaseException | None = None) -> None:
        self.failure = failure
        self.messages: list[RenderedMessage] = []

    async def send_issue(self, message: RenderedMessage) -> SlackReceipt:
        self.messages.append(message)
        if self.failure:
            raise self.failure
        return SlackReceipt(channel="CISSUES", ts="123.456")


def completed_bucket(redis: FakeRedis) -> str:
    event = IssueEvent.create(
        kind=IssueKind.RETRY_SCHEDULED,
        service="celery",
        operation="ohlcv.collect_overseas_daily",
        observed_at=datetime(2026, 8, 3, 4, 15, tzinfo=UTC),
    )
    key = "news2:notifications:issues:3600:1785729600:events"
    redis.values[key] = [event.model_dump_json()]
    return key.removesuffix(":events")


@pytest.mark.asyncio
async def test_service_sends_completed_bucket_and_marks_it_sent() -> None:
    redis = FakeRedis()
    key_base = completed_bucket(redis)
    gateway = RecordingSlackGateway()
    service = IssueDigestService(
        enabled=True,
        aggregator=IssueAggregator(redis=redis, retention_seconds=86400),
        analyzer=StaticAnalyzer(),
        slack_gateway=gateway,
    )

    sent_count = await service.run(now=datetime(2026, 8, 3, 6, 0, tzinfo=UTC))

    assert sent_count == 1
    assert len(gateway.messages) == 1
    assert await redis.get(f"{key_base}:sent") == '{"channel":"CISSUES","ts":"123.456"}'
    assert await redis.get(f"{key_base}:lock") is None


@pytest.mark.asyncio
async def test_service_releases_lock_without_marking_sent_when_slack_fails() -> None:
    redis = FakeRedis()
    key_base = completed_bucket(redis)
    service = IssueDigestService(
        enabled=True,
        aggregator=IssueAggregator(redis=redis, retention_seconds=86400),
        analyzer=StaticAnalyzer(),
        slack_gateway=RecordingSlackGateway(failure=SlackDeliveryError("timeout")),
    )

    sent_count = await service.run(now=datetime(2026, 8, 3, 6, 0, tzinfo=UTC))

    assert sent_count == 0
    assert await redis.get(f"{key_base}:sent") is None
    assert await redis.get(f"{key_base}:lock") is None


@pytest.mark.asyncio
async def test_disabled_service_does_not_read_redis() -> None:
    class UnexpectedAggregator:
        async def pending_buckets(self, _: datetime):
            raise AssertionError("disabled service must not access Redis")

    service = IssueDigestService(
        enabled=False,
        aggregator=UnexpectedAggregator(),  # type: ignore[arg-type]
        analyzer=StaticAnalyzer(),
        slack_gateway=RecordingSlackGateway(),
    )

    assert await service.run() == 0

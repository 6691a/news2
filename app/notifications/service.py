"""완료된 운영 이슈 버킷의 분석과 Slack 전송을 조율한다."""

from datetime import UTC, datetime
from typing import Protocol

import sentry_sdk

from app.core.logging import get_logger
from app.notifications.aggregator import IssueAggregator, IssueBucket
from app.notifications.llm import IssueAnalyzer, analyze_with_fallback
from app.notifications.models import IssueDigest
from app.notifications.slack import RenderedMessage, SlackGateway, SlackReceipt
from app.notifications.templates import render_issue_digest


logger = get_logger(__name__)


class DigestAggregator(Protocol):
    """Digest 서비스가 사용하는 집계 저장소 계약."""

    async def pending_buckets(self, now: datetime) -> list[IssueBucket]:
        """완료됐지만 전송되지 않은 버킷을 반환한다."""

    async def acquire(self, bucket: IssueBucket) -> str | None:
        """버킷 잠금을 획득하고 소유 토큰을 반환한다."""

    async def release(self, bucket: IssueBucket, token: str) -> None:
        """소유 중인 버킷 잠금을 해제한다."""

    async def build_digest(self, bucket: IssueBucket) -> IssueDigest:
        """버킷 이벤트를 digest로 집계한다."""

    async def mark_sent(self, bucket: IssueBucket, receipt: SlackReceipt) -> None:
        """성공한 Slack 전송 영수증을 저장한다."""


class IssueSlackGateway(Protocol):
    """Issue 채널에 렌더링된 메시지를 전송하는 계약."""

    async def send_issue(self, message: RenderedMessage) -> SlackReceipt:
        """Issue 메시지를 전송한다."""


class IssueDigestService:
    """잠금, 분석, 전송, 전송 표시를 안전한 순서로 실행한다."""

    def __init__(
        self,
        *,
        enabled: bool,
        aggregator: DigestAggregator | IssueAggregator,
        analyzer: IssueAnalyzer,
        slack_gateway: IssueSlackGateway | SlackGateway,
    ) -> None:
        """알림 활성화 상태와 처리 의존성을 저장한다."""

        self.enabled = enabled
        self.aggregator = aggregator
        self.analyzer = analyzer
        self.slack_gateway = slack_gateway

    async def run(self, *, now: datetime | None = None) -> int:
        """현재까지 완료된 버킷을 처리하고 성공 전송 수를 반환한다."""

        if not self.enabled:
            return 0
        current_time = now or datetime.now(UTC)
        try:
            buckets = await self.aggregator.pending_buckets(current_time)
        except Exception as exc:
            self._capture_failure(exc, stage="discover")
            return 0

        sent_count = 0
        for bucket in buckets:
            token = await self.aggregator.acquire(bucket)
            if token is None:
                continue
            try:
                digest = await self.aggregator.build_digest(bucket)
                analysis = await analyze_with_fallback(self.analyzer, digest)
                receipt = await self.slack_gateway.send_issue(render_issue_digest(digest, analysis))
                await self.aggregator.mark_sent(bucket, receipt)
                sent_count += 1
            except Exception as exc:
                self._capture_failure(exc, stage="process", bucket=bucket)
            finally:
                try:
                    await self.aggregator.release(bucket, token)
                except Exception as exc:
                    self._capture_failure(exc, stage="release", bucket=bucket)
        return sent_count

    @staticmethod
    def _capture_failure(exc: Exception, *, stage: str, bucket: IssueBucket | None = None) -> None:
        logger.exception(
            "issue_digest_processing_failed",
            stage=stage,
            bucket_key=bucket.events_key if bucket else None,
            error_type=type(exc).__name__,
        )
        sentry_sdk.capture_exception(exc)

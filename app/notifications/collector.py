"""운영 이슈를 Redis 시간 버킷에 기록."""

from typing import Protocol

import sentry_sdk
from redis.exceptions import RedisError

from app.core.logging import get_logger
from app.notifications.models import IssueEvent
from app.notifications.redaction import redact_issue_context


logger = get_logger(__name__)
KEY_PREFIX = "news2:notifications:issues"


class IssueRedisWriter(Protocol):
    """IssueCollector가 사용하는 Redis 쓰기 범위."""

    async def rpush(self, key: str, value: str) -> int:
        """List 끝에 이벤트를 추가한다."""

    async def expire(self, key: str, seconds: int) -> bool:
        """키 만료 시간을 지정한다."""


class IssueEventRecorder(Protocol):
    """운영 이슈 발생 지점이 의존하는 최소 기록 계약."""

    async def record(self, event: IssueEvent) -> bool:
        """이슈 이벤트를 기록하고 성공 여부를 반환한다."""


class NoopIssueCollector:
    """알림 인프라를 주입하지 않은 실행 경로의 무동작 기록기."""

    async def record(self, event: IssueEvent) -> bool:
        """이벤트를 버리고 False를 반환한다."""

        del event
        return False


async def safe_record_issue(recorder: IssueEventRecorder, event: IssueEvent) -> bool:
    """기록기 자체의 예외가 원래 수집 작업으로 전파되지 않게 격리한다."""

    try:
        return await recorder.record(event)
    except Exception as error:
        logger.exception(
            "issue_event_record_failed",
            service=event.service,
            operation=event.operation,
            error_type=type(error).__name__,
        )
        sentry_sdk.capture_exception(error)
        return False


class IssueCollector:
    """검증·정제된 IssueEvent를 Redis 버킷에 기록한다."""

    def __init__(self, *, redis: IssueRedisWriter, interval_seconds: int, retention_seconds: int) -> None:
        """Redis 의존성과 버킷·보존 간격을 설정한다."""

        self.redis = redis
        self.interval_seconds = interval_seconds
        self.retention_seconds = retention_seconds

    def events_key(self, event: IssueEvent) -> str:
        """이벤트 시각이 속한 Redis List 키를 반환한다."""

        epoch = int(event.observed_at.timestamp())
        bucket_start = epoch // self.interval_seconds * self.interval_seconds
        return f"{KEY_PREFIX}:{self.interval_seconds}:{bucket_start}:events"

    async def record(self, event: IssueEvent) -> bool:
        """이벤트를 기록하고 인프라 실패 시 False를 반환한다."""

        safe_event = event.model_copy(update={"context": redact_issue_context(event.context)})
        key = self.events_key(safe_event)
        try:
            await self.redis.rpush(key, safe_event.model_dump_json())
            await self.redis.expire(key, self.retention_seconds)
        except (RedisError, OSError) as error:
            logger.exception(
                "issue_event_record_failed",
                service=event.service,
                operation=event.operation,
                error_type=type(error).__name__,
            )
            sentry_sdk.capture_exception(error)
            return False

        logger.info("issue_event_recorded", service=event.service, operation=event.operation)
        return True

"""Redis 시간 버킷 탐색, 운영 이슈 그룹화, 전달 상태 관리."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
from typing import Protocol
from uuid import uuid4

from app.notifications.collector import KEY_PREFIX
from app.notifications.models import IssueDigest, IssueEvent, IssueGroup, IssueSeverity
from app.notifications.slack import SlackReceipt


class IssueRedisStore(Protocol):
    """IssueAggregator가 사용하는 Redis 명령 범위."""

    def scan_iter(self, match: str) -> object:
        """패턴과 일치하는 키의 비동기 iterator를 반환한다."""

    async def lrange(self, key: str, start: int, end: int) -> list[str]:
        """List 범위를 읽는다."""

    async def get(self, key: str) -> object | None:
        """문자열 값을 읽는다."""

    async def set(
        self,
        key: str,
        value: object,
        *,
        nx: bool = False,
        ex: int | None = None,
    ) -> bool | None:
        """문자열 값과 선택적 잠금·만료 조건을 설정한다."""

    async def delete(self, key: str) -> int:
        """키를 삭제한다."""

    async def expire(self, key: str, seconds: int) -> bool:
        """키 만료 시간을 지정한다."""


@dataclass(frozen=True, slots=True)
class IssueBucket:
    """Redis에 저장된 한 완료 시간 버킷."""

    interval_seconds: int
    bucket_start_epoch: int
    events_key: str

    @classmethod
    def parse(cls, key: str) -> "IssueBucket":
        """표준 Redis events 키를 버킷 값으로 파싱한다."""

        prefix, interval, bucket_start, suffix = key.rsplit(":", 3)
        if prefix != KEY_PREFIX or suffix != "events":
            raise ValueError(f"invalid issue events key: {key}")
        return cls(interval_seconds=int(interval), bucket_start_epoch=int(bucket_start), events_key=key)

    @property
    def window_start(self) -> datetime:
        """버킷 시작 UTC 시각."""

        return datetime.fromtimestamp(self.bucket_start_epoch, UTC)

    @property
    def window_end(self) -> datetime:
        """버킷 종료 UTC 시각."""

        return self.window_start + timedelta(seconds=self.interval_seconds)

    @property
    def key_base(self) -> str:
        """상태 키가 공유하는 접두 문자열."""

        return self.events_key.removesuffix(":events")

    @property
    def lock_key(self) -> str:
        """분산 잠금 키."""

        return f"{self.key_base}:lock"

    @property
    def sent_key(self) -> str:
        """Slack 전달 완료 표식 키."""

        return f"{self.key_base}:sent"


class IssueAggregator:
    """완료 버킷을 찾고 이벤트를 fingerprint 단위로 집계한다."""

    def __init__(self, *, redis: IssueRedisStore, retention_seconds: int, lock_seconds: int = 300) -> None:
        """Redis 저장소와 상태 보존·잠금 시간을 설정한다."""

        self.redis = redis
        self.retention_seconds = retention_seconds
        self.lock_seconds = lock_seconds

    async def pending_buckets(self, now: datetime) -> list[IssueBucket]:
        """현재 시각 전에 닫혔고 아직 보내지 않은 모든 간격의 버킷을 찾는다."""

        buckets: list[IssueBucket] = []
        async for raw_key in self.redis.scan_iter(match=f"{KEY_PREFIX}:*:events"):  # type: ignore[attr-defined]
            key = raw_key.decode() if isinstance(raw_key, bytes) else str(raw_key)
            try:
                bucket = IssueBucket.parse(key)
            except ValueError:
                continue
            if bucket.window_end > now.astimezone(UTC):
                continue
            if await self.redis.get(bucket.sent_key) is not None:
                continue
            buckets.append(bucket)
        return sorted(buckets, key=lambda item: (item.bucket_start_epoch, item.interval_seconds))

    async def acquire(self, bucket: IssueBucket) -> str | None:
        """버킷 처리 잠금을 얻고 소유 토큰을 반환한다."""

        token = uuid4().hex
        acquired = await self.redis.set(bucket.lock_key, token, nx=True, ex=self.lock_seconds)
        return token if acquired else None

    async def release(self, bucket: IssueBucket, token: str) -> None:
        """호출자가 소유한 버킷 잠금만 해제한다."""

        if await self.redis.get(bucket.lock_key) == token:
            await self.redis.delete(bucket.lock_key)

    async def build_digest(self, bucket: IssueBucket) -> IssueDigest:
        """버킷 이벤트를 fingerprint별 IssueGroup으로 집계한다."""

        raw_events = await self.redis.lrange(bucket.events_key, 0, -1)
        events = [
            IssueEvent.model_validate_json(item.decode() if isinstance(item, bytes) else item) for item in raw_events
        ]
        grouped: dict[str, list[IssueEvent]] = defaultdict(list)
        for event in events:
            grouped[event.fingerprint].append(event)

        groups: list[IssueGroup] = []
        for fingerprint, items in sorted(grouped.items()):
            ordered = sorted(items, key=lambda item: item.observed_at)
            severity = (
                IssueSeverity.HIGH
                if any(item.severity is IssueSeverity.HIGH for item in ordered)
                else IssueSeverity.WARNING
            )
            contexts = []
            for item in ordered:
                if item.context and item.context not in contexts:
                    contexts.append(item.context)
                if len(contexts) == 5:
                    break
            groups.append(
                IssueGroup(
                    fingerprint=fingerprint,
                    kind=ordered[0].kind,
                    severity=severity,
                    count=len(ordered),
                    first_observed_at=ordered[0].observed_at,
                    last_observed_at=ordered[-1].observed_at,
                    services=sorted({item.service for item in ordered}),
                    operations=sorted({item.operation for item in ordered}),
                    contexts=contexts,
                )
            )

        digest_id = f"issue-{bucket.window_start.strftime('%Y%m%dT%H%M%SZ')}-{bucket.interval_seconds}"
        return IssueDigest(
            digest_id=digest_id,
            window_start=bucket.window_start,
            window_end=bucket.window_end,
            total_events=len(events),
            groups=groups,
        )

    async def mark_sent(self, bucket: IssueBucket, receipt: SlackReceipt) -> None:
        """Slack 성공 영수증을 저장해 같은 버킷의 재전송을 막는다."""

        value = json.dumps({"channel": receipt.channel, "ts": receipt.ts}, separators=(",", ":"))
        await self.redis.set(bucket.sent_key, value)
        await self.redis.expire(bucket.sent_key, self.retention_seconds)

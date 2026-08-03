from collections.abc import AsyncIterator
from fnmatch import fnmatch

from app.notifications.models import IssueEvent


class RecordingIssueCollector:
    def __init__(self) -> None:
        self.events: list[IssueEvent] = []

    async def record(self, event: IssueEvent) -> bool:
        self.events.append(event)
        return True


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}
        self.expiries: dict[str, int] = {}
        self.fail_writes = False

    async def rpush(self, key: str, value: str) -> int:
        if self.fail_writes:
            raise ConnectionError("redis unavailable")
        items = self.values.setdefault(key, [])
        assert isinstance(items, list)
        items.append(value)
        return len(items)

    async def expire(self, key: str, seconds: int) -> bool:
        self.expiries[key] = seconds
        return True

    async def lrange(self, key: str, start: int, end: int) -> list[str]:
        del start, end
        items = self.values.get(key, [])
        assert isinstance(items, list)
        return list(items)

    async def get(self, key: str) -> object | None:
        return self.values.get(key)

    async def set(
        self,
        key: str,
        value: object,
        *,
        nx: bool = False,
        ex: int | None = None,
    ) -> bool | None:
        if nx and key in self.values:
            return None
        self.values[key] = value
        if ex is not None:
            self.expiries[key] = ex
        return True

    async def delete(self, key: str) -> int:
        existed = key in self.values
        self.values.pop(key, None)
        return int(existed)

    async def scan_iter(self, match: str) -> AsyncIterator[str]:
        for key in sorted(self.values):
            if fnmatch(key, match):
                yield key

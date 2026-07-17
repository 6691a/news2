from collections.abc import AsyncIterator
from datetime import datetime

import pytest
from dependency_injector import providers
from sqlalchemy.exc import SQLAlchemyError

from app.core.containers import container
from app.kis.korea.__main__ import main
from app.kis.korea.schemas import (
    KISKoreaOrderbook,
    KISKoreaSubscription,
    KISKoreaTrade,
    KISKoreaTrId,
    parse_frame,
)
from tests.kis.korea.fixtures import SK_HYNIX_TRADE_FRAMES


class FakeDatabase:
    """메인 프로세스의 DB 풀 종료 여부를 기록한다."""

    def __init__(self) -> None:
        self.disposed = False

    async def dispose(self) -> None:
        """DB 풀 종료 호출을 기록한다."""

        self.disposed = True


class FakeRepository:
    """첫 저장만 실패시키고 이후 호출을 기록한다."""

    def __init__(self) -> None:
        self.calls: list[tuple[KISKoreaTrade | KISKoreaOrderbook, datetime]] = []

    async def save(
        self,
        event: KISKoreaTrade | KISKoreaOrderbook,
        received_at: datetime,
    ) -> None:
        """호출을 기록하고 첫 저장에서 DB 오류를 발생시킨다."""

        self.calls.append((event, received_at))
        if len(self.calls) == 1:
            raise SQLAlchemyError("database unavailable")


@pytest.mark.asyncio
async def test_main_continues_after_tick_save_failure_and_disposes_database() -> None:
    events: list[KISKoreaTrade | KISKoreaOrderbook] = []
    subscriptions: list[KISKoreaSubscription] = []
    for frame in SK_HYNIX_TRADE_FRAMES[:2]:
        parsed = parse_frame(frame)
        assert parsed is not None
        events.append(parsed[0])
    repository = FakeRepository()
    database = FakeDatabase()

    class FakeQuote:
        async def subscribe(self, subscription: KISKoreaSubscription) -> None:
            subscriptions.append(subscription)

        async def run(self) -> None:
            return None

        async def stream(self) -> AsyncIterator[KISKoreaTrade | KISKoreaOrderbook]:
            for event in events:
                yield event

    with (
        container.korea_websocket_quote.override(providers.Object(FakeQuote())),
        container.korea_tick_repository.override(providers.Object(repository)),
        container.database.override(providers.Object(database)),
    ):
        await main()

    assert [event for event, _ in repository.calls] == events
    assert {subscription.tr_id for subscription in subscriptions} == {
        KISKoreaTrId.STOCK_TRADE_KRX,
        KISKoreaTrId.STOCK_ORDERBOOK_KRX,
    }
    assert all(received_at.utcoffset() is not None for _, received_at in repository.calls)
    assert database.disposed is True

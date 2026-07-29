import pytest
from dependency_injector import providers

from app.core.containers import Container
from app.instruments.repository import InstrumentRepository
from app.kis.auth import KISAuth
from app.kis.korea.quote import KISKoreaWebSocketQuote
from app.kis.korea.repository import KISKoreaTickRepository
from app.kis.overseas.quote import KISOverseasWebSocketQuote
from app.kis.overseas.repository import KISOverseasTickRepository
from app.kis.schemas import KISWebSocketTokenResponse
from app.macro.us_treasury.service import UsTreasuryYieldService


def test_container_provides_instrument_repository() -> None:
    container = Container()

    repository = container.instrument_repository()

    assert isinstance(repository, InstrumentRepository)


def test_container_provides_kis_tick_repositories() -> None:
    container = Container()

    korea_repository = container.korea_tick_repository()
    overseas_repository = container.overseas_tick_repository()

    assert isinstance(korea_repository, KISKoreaTickRepository)
    assert isinstance(overseas_repository, KISOverseasTickRepository)


def test_container_provides_korea_investor_flow_service() -> None:
    from app.kis.korea.investor.service import KISKoreaInvestorFlowService

    container = Container()

    service = container.korea_investor_flow_service()

    assert isinstance(service, KISKoreaInvestorFlowService)
    assert service.settings is container.settings()
    assert isinstance(service.auth, KISAuth)


def test_container_provides_treasury_service_without_cookie_dependency() -> None:
    container = Container()

    service = container.us_treasury_yield_service()

    assert isinstance(service, UsTreasuryYieldService)
    assert service.settings is container.settings()


@pytest.mark.asyncio
async def test_container_provides_kis_auth_and_websocket_quotes() -> None:
    container = Container()
    token = KISWebSocketTokenResponse(approval_key="test-approval-key")

    class FakeAuth:
        async def get_websocket_token(self) -> KISWebSocketTokenResponse:
            return token

    with container.kis_auth.override(providers.Object(FakeAuth())):
        korea_quote = await container.korea_websocket_quote.async_()
        overseas_quote = await container.overseas_websocket_quote.async_()

    assert isinstance(container.kis_auth(), KISAuth)
    assert isinstance(korea_quote, KISKoreaWebSocketQuote)
    assert korea_quote.token is token
    assert isinstance(overseas_quote, KISOverseasWebSocketQuote)
    assert overseas_quote.token is token

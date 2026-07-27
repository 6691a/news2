from dependency_injector import containers, providers
from redis.asyncio import Redis

from app.core.config import settings as app_settings
from app.core.database import Database
from app.instruments.repository import InstrumentRepository
from app.kis.auth import KISAuth
from app.kis.korea.investor.repository import KISInvestorFlowRepository
from app.kis.korea.investor.service import KISKoreaInvestorFlowService
from app.kis.korea.quote import KISKoreaWebSocketQuote
from app.kis.korea.repository import KISKoreaTickRepository
from app.kis.overseas.quote import KISOverseasWebSocketQuote
from app.kis.overseas.repository import KISOverseasTickRepository
from app.kis.schemas import KISWebSocketTokenResponse


async def provide_websocket_token(auth: KISAuth) -> KISWebSocketTokenResponse:
    """KIS 인증 객체로 WebSocket 승인 키를 발급한다."""

    return await auth.get_websocket_token()


class Container(containers.DeclarativeContainer):
    """애플리케이션 인프라 의존성을 조립한다."""

    settings = providers.Object(app_settings)
    database = providers.Singleton(
        Database,
        database_url=settings.provided.database_url,
    )
    # 연결 풀을 재사용해야 하므로 Singleton이다.
    redis_client = providers.Singleton(
        Redis.from_url,
        settings.provided.redis_url,
        decode_responses=True,
    )
    kis_auth = providers.Factory(
        KISAuth,
        settings=settings,
        redis=redis_client,
    )
    korea_investor_flow_service = providers.Factory(
        KISKoreaInvestorFlowService,
        settings=settings,
        auth=kis_auth,
    )
    websocket_token = providers.Coroutine(
        provide_websocket_token,
        auth=kis_auth,
    )
    korea_websocket_quote = providers.Factory(
        KISKoreaWebSocketQuote,
        settings=settings,
        token=websocket_token,
    )
    overseas_websocket_quote = providers.Factory(
        KISOverseasWebSocketQuote,
        settings=settings,
        token=websocket_token,
    )
    korea_tick_repository = providers.Factory(
        KISKoreaTickRepository,
        session_factory=database.provided.session_factory,
    )
    overseas_tick_repository = providers.Factory(
        KISOverseasTickRepository,
        session_factory=database.provided.session_factory,
    )
    instrument_repository = providers.Factory(
        InstrumentRepository,
        session_factory=database.provided.session_factory,
    )
    korea_investor_flow_repository = providers.Factory(
        KISInvestorFlowRepository,
        session_factory=database.provided.session_factory,
    )


container = Container()

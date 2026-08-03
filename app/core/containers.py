from dependency_injector import containers, providers
from redis.asyncio import Redis
from slack_sdk.web.async_client import AsyncWebClient

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
from app.macro.us.treasury.repository import UsTreasuryYieldRepository
from app.macro.us.treasury.service import UsTreasuryYieldService
from app.notifications.aggregator import IssueAggregator
from app.notifications.collector import IssueCollector
from app.notifications.llm import OpenAIResponsesIssueAnalyzer
from app.notifications.service import IssueDigestService
from app.notifications.slack import SlackGateway
from app.ohlcv.korea import KISKoreaDailyChartService
from app.ohlcv.overseas import YahooDailyChartService
from app.ohlcv.repository import OhlcvRepository


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
    issue_collector = providers.Factory(
        IssueCollector,
        redis=redis_client,
        interval_seconds=settings.provided.issue_digest_interval_seconds,
        retention_seconds=settings.provided.issue_event_retention_seconds,
    )
    issue_aggregator = providers.Factory(
        IssueAggregator,
        redis=redis_client,
        retention_seconds=settings.provided.issue_event_retention_seconds,
    )
    issue_llm_analyzer = providers.Factory(
        OpenAIResponsesIssueAnalyzer,
        api_key=settings.provided.openai_api_key,
        model=settings.provided.issue_llm_model,
        timeout_seconds=settings.provided.issue_llm_timeout_seconds,
        max_groups=settings.provided.issue_llm_max_groups,
    )
    slack_client = providers.Factory(
        AsyncWebClient,
        token=settings.provided.slack_bot_token,
    )
    slack_gateway = providers.Factory(
        SlackGateway,
        client=slack_client,
        issues_channel_id=settings.provided.slack_issues_channel_id,
        reports_channel_id=settings.provided.slack_reports_channel_id,
    )
    issue_digest_service = providers.Factory(
        IssueDigestService,
        enabled=settings.provided.slack_notifications_enabled,
        aggregator=issue_aggregator,
        analyzer=issue_llm_analyzer,
        slack_gateway=slack_gateway,
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
        issue_collector=issue_collector,
    )
    overseas_websocket_quote = providers.Factory(
        KISOverseasWebSocketQuote,
        settings=settings,
        token=websocket_token,
        issue_collector=issue_collector,
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
    us_treasury_yield_service = providers.Factory(
        UsTreasuryYieldService,
        settings=settings,
    )
    us_treasury_yield_repository = providers.Factory(
        UsTreasuryYieldRepository,
        session_factory=database.provided.session_factory,
    )
    korea_daily_chart_service = providers.Factory(
        KISKoreaDailyChartService,
        settings=settings,
        auth=kis_auth,
    )
    overseas_daily_chart_service = providers.Factory(YahooDailyChartService)
    ohlcv_repository = providers.Factory(
        OhlcvRepository,
        session_factory=database.provided.session_factory,
    )


container = Container()

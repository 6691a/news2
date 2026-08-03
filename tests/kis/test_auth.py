import json
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import status
import httpx
import pytest
from redis.asyncio import Redis

from app.core.config import Settings
from app.kis.auth import KISAuth


def _settings(kis_virtual: bool = False) -> Settings:
    """KIS 인증 테스트용 설정을 반환한다.

    Args:
        kis_virtual: 모의투자 도메인을 쓸지 여부.

    Returns:
        테스트 전용 설정 인스턴스.
    """

    return Settings(
        sentry_dsn='https://public@example.ingest.sentry.io/1',
        sentry_environment='test',
        sentry_release='news2@test',
        sentry_traces_sample_rate=0.0,
        sentry_error_sample_rate=0.0,
        database_url="postgresql+asyncpg://user:pass@localhost/news2",
        kis_virtual=kis_virtual,
        kis_app_key="app-key",
        kis_app_secret="app-secret",
        kis_rest_domain="https://rest.example",
        kis_websocket_domain="wss://websocket.example",
        kis_virtual_rest_domain="https://virtual-rest.example",
        kis_virtual_websocket_domain="wss://virtual-websocket.example",
    )


def _mock_redis(cached: str | None = None) -> AsyncMock:
    """지정한 값을 캐시로 돌려주는 Redis 스텁을 만든다.

    Args:
        cached: `get`이 반환할 문자열. `None`이면 캐시 미스.

    Returns:
        `Redis` 인터페이스를 흉내내는 비동기 mock.
    """

    # redis-py의 `get`/`set`은 `async def`가 아니라 awaitable을 돌려주는 일반
    # 메서드라 spec만으로는 AsyncMock이 되지 않는다. 명시적으로 교체한다.
    redis = AsyncMock(spec=Redis)
    redis.get = AsyncMock(return_value=cached)
    redis.set = AsyncMock(return_value=True)
    return redis


def _token_body(expires_in: float = 86400) -> dict[str, object]:
    """토큰 발급 응답 본문을 만든다.

    Args:
        expires_in: 응답에 담을 잔여 유효 시간(초).

    Returns:
        `KISAuthTokenResponse` 필드를 채운 JSON 본문.
    """

    return {
        "access_token": "access-token",
        "token_type": "Bearer",
        "expires_in": expires_in,
        "access_token_token_expired": "2026-07-18 12:00:00",
    }


def _mock_client(response_body: dict[str, object]) -> tuple[AsyncMock, MagicMock]:
    """지정한 JSON 본문을 반환하는 비동기 HTTP 클라이언트를 만든다."""

    response = MagicMock(spec=httpx.Response)
    response.json.return_value = response_body
    # spec mock의 is_error는 기본이 truthy라 성공 응답임을 명시해야 한다.
    response.is_error = False
    response.status_code = status.HTTP_200_OK
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.return_value = response
    context_manager = MagicMock()
    context_manager.__aenter__ = AsyncMock(return_value=client)
    context_manager.__aexit__ = AsyncMock(return_value=None)
    return client, context_manager


@pytest.mark.asyncio
async def test_get_auth_token_requests_and_parses_rest_token() -> None:
    client, context_manager = _mock_client(_token_body())
    auth = KISAuth(_settings(), _mock_redis())

    with patch("app.kis.auth.httpx.AsyncClient", return_value=context_manager):
        token = await auth.get_auth_token()

    assert token.access_token == "access-token"
    client.post.assert_awaited_once_with(
        headers={
            "Content-Type": "application/json",
            "Accept": "text/plain",
            "charset": "UTF-8",
        },
        url="https://rest.example/oauth2/tokenP",
        json={
            "appkey": "app-key",
            "appsecret": "app-secret",
            "grant_type": "client_credentials",
        },
    )


@pytest.mark.asyncio
async def test_get_auth_token_reuses_cached_token_without_http_request() -> None:
    # 캐시가 살아 있으면 KIS 발급 API를 아예 부르지 않아야 1분 제한을 밟지 않는다.
    redis = _mock_redis(json.dumps(_token_body()))
    auth = KISAuth(_settings(), redis)

    with patch("app.kis.auth.httpx.AsyncClient") as client_factory:
        token = await auth.get_auth_token()

    assert token.access_token == "access-token"
    client_factory.assert_not_called()
    redis.set.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_auth_token_caches_issued_token_with_margin_ttl() -> None:
    client, context_manager = _mock_client(_token_body())
    redis = _mock_redis()
    auth = KISAuth(_settings(), redis)

    with patch("app.kis.auth.httpx.AsyncClient", return_value=context_manager):
        token = await auth.get_auth_token()

    client.post.assert_awaited_once()
    redis.set.assert_awaited_once_with(
        "kis:auth:token:real:2924a27d7fc7",
        token.model_dump_json(),
        ex=86400 - 600,
    )


@pytest.mark.asyncio
async def test_get_auth_token_skips_cache_when_expiry_is_within_margin() -> None:
    # TTL이 0 이하가 되면 Redis가 거부하므로 마진보다 짧은 토큰은 캐시하지 않는다.
    _, context_manager = _mock_client(_token_body(expires_in=600))
    redis = _mock_redis()
    auth = KISAuth(_settings(), redis)

    with patch("app.kis.auth.httpx.AsyncClient", return_value=context_manager):
        token = await auth.get_auth_token()

    assert token.expires_in == 600
    redis.set.assert_not_awaited()


def test_token_cache_key_separates_virtual_and_real_environments() -> None:
    # 앱키를 바꾸면 키도 바뀌어 이전 환경 토큰이 조용히 재사용되지 않는다.
    real_key = KISAuth(_settings(kis_virtual=False), _mock_redis())._token_cache_key
    virtual_key = KISAuth(_settings(kis_virtual=True), _mock_redis())._token_cache_key

    assert real_key.startswith("kis:auth:token:real:")
    assert virtual_key.startswith("kis:auth:token:virtual:")
    assert real_key != virtual_key


@pytest.mark.asyncio
async def test_remove_auth_token_requests_token_revocation() -> None:
    client, context_manager = _mock_client({"code": status.HTTP_200_OK, "message": "success"})
    auth = KISAuth(_settings(), _mock_redis())

    with patch("app.kis.auth.httpx.AsyncClient", return_value=context_manager):
        result = await auth.remove_auth_token("access-token")

    assert result.code == status.HTTP_200_OK
    client.post.assert_awaited_once_with(
        headers={
            "Content-Type": "application/json",
            "Accept": "text/plain",
            "charset": "UTF-8",
        },
        url="https://rest.example/oauth2/revokeP",
        json={
            "appkey": "app-key",
            "appsecret": "app-secret",
            "token": "access-token",
        },
    )

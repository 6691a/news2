from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.core.config import Settings
from app.kis.auth import KISAuth


def _settings() -> Settings:
    """KIS 인증 테스트용 설정을 반환한다."""

    return Settings(
        database_url="postgresql+asyncpg://user:pass@localhost/news2",
        kis_virtual=False,
        kis_app_key="app-key",
        kis_app_secret="app-secret",
        kis_rest_domain="https://rest.example",
        kis_websocket_domain="wss://websocket.example",
        kis_virtual_rest_domain="https://virtual-rest.example",
        kis_virtual_websocket_domain="wss://virtual-websocket.example",
    )


def _mock_client(response_body: dict[str, object]) -> tuple[AsyncMock, MagicMock]:
    """지정한 JSON 본문을 반환하는 비동기 HTTP 클라이언트를 만든다."""

    response = MagicMock(spec=httpx.Response)
    response.json.return_value = response_body
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.return_value = response
    context_manager = MagicMock()
    context_manager.__aenter__ = AsyncMock(return_value=client)
    context_manager.__aexit__ = AsyncMock(return_value=None)
    return client, context_manager


@pytest.mark.asyncio
async def test_get_auth_token_requests_and_parses_rest_token() -> None:
    client, context_manager = _mock_client(
        {
            "access_token": "access-token",
            "token_type": "Bearer",
            "expires_in": 86400,
            "access_token_token_expired": "2026-07-18 12:00:00",
        }
    )
    auth = KISAuth(_settings())

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
async def test_remove_auth_token_requests_token_revocation() -> None:
    client, context_manager = _mock_client({"code": 200, "message": "success"})
    auth = KISAuth(_settings())

    with patch("app.kis.auth.httpx.AsyncClient", return_value=context_manager):
        result = await auth.remove_auth_token("access-token")

    assert result.code == 200
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

from enum import StrEnum

import httpx

from app.core.config import Settings
from app.kis.schemas import (
    KISAuthRequest,
    KISAuthTokenRemoveRequest,
    KISAuthTokenRemoveResponse,
    KISAuthTokenResponse,
    KISBaseAuthTokenHeader,
    KISWebSocketTokenResponse,
    KISWebSocketTokenRequest,
)


class KISAuth:
    class KISEndpoint(StrEnum):
        AUTH_TOKEN = "/oauth2/tokenP"
        REMOVE_AUTH_TOKEN = "/oauth2/revokeP"
        WEBSOCKET_TOKEN = "/oauth2/Approval"

    def __init__(self, settings: Settings):
        self.kis_virtual = settings.kis_virtual
        self.app_key = settings.kis_app_key
        self.app_secret = settings.kis_app_secret
        self.rest_domain = settings.kis_rest_domain
        self.websocket_domain = settings.kis_websocket_domain
        self.virtual_rest_domain = settings.kis_virtual_rest_domain
        self.virtual_websocket_domain = settings.kis_virtual_websocket_domain

    def _get_domain(self) -> str:
        """
        가상 투자 여부에 따라 REST 도메인을 반환한다.

        `kis_virtual` 속성이 `True`이면 가상 도메인 값을, 그렇지 않으면
        실전 도메인 값을 반환한다.

        Returns:
            str: (REST 도메인)
        """

        if self.kis_virtual:
            return self.virtual_rest_domain
        else:
            return self.rest_domain

    async def get_auth_token(self) -> KISAuthTokenResponse:
        """앱 키·시크릿으로 REST API 접근 토큰을 발급받는다.

        Returns:
            발급된 access token과 만료 정보를 담은 응답.

        Raises:
            httpx.HTTPStatusError: 인증 요청이 실패한 경우.
        """
        domain = self._get_domain()
        end_point = self.KISEndpoint.AUTH_TOKEN
        url = f"{domain}{end_point}"

        body = KISAuthRequest(
            app_key=self.app_key,
            app_secret=self.app_secret,
        ).model_dump()
        headers = KISBaseAuthTokenHeader().model_dump()

        async with httpx.AsyncClient() as client:
            response = await client.post(
                headers=headers,
                url=url,
                json=body,
            )
            response.raise_for_status()
            return KISAuthTokenResponse(**response.json())

    async def remove_auth_token(self, access_token: str) -> KISAuthTokenRemoveResponse:
        """발급받은 REST API 접근 토큰을 폐기한다.

        Args:
            access_token: 폐기할 access token.

        Returns:
            토큰 폐기 처리 결과 응답.

        Raises:
            httpx.HTTPStatusError: 폐기 요청이 실패한 경우.
        """
        domain = self._get_domain()
        end_point = self.KISEndpoint.REMOVE_AUTH_TOKEN
        url = f"{domain}{end_point}"

        headers = KISBaseAuthTokenHeader().model_dump()
        body = KISAuthTokenRemoveRequest(
            app_key=self.app_key,
            app_secret=self.app_secret,
            token=access_token,
        ).model_dump()

        async with httpx.AsyncClient() as client:
            response = await client.post(
                headers=headers,
                url=url,
                json=body,
            )
            response.raise_for_status()
            return KISAuthTokenRemoveResponse(**response.json())

    async def get_websocket_token(self) -> KISWebSocketTokenResponse:
        """실시간 시세용 WebSocket 접속키(approval key)를 발급받는다.

        Returns:
            WebSocket 접속에 사용할 approval key를 담은 응답.

        Raises:
            httpx.HTTPStatusError: 발급 요청이 실패한 경우.
        """
        domain = self._get_domain()
        end_point = self.KISEndpoint.WEBSOCKET_TOKEN
        url = f"{domain}{end_point}"

        headers = KISBaseAuthTokenHeader().model_dump()
        body = KISWebSocketTokenRequest(
            app_key=self.app_key,
            app_secret=self.app_secret,
        ).model_dump()

        async with httpx.AsyncClient() as client:
            response = await client.post(
                headers=headers,
                url=url,
                json=body,
            )
            response.raise_for_status()
            return KISWebSocketTokenResponse(**response.json())

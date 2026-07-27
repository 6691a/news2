import hashlib
from enum import StrEnum

import httpx
from redis.asyncio import Redis

from app.core.config import Settings
from app.core.logging import get_logger
from app.kis.schemas import (
    KISAuthRequest,
    KISAuthTokenRemoveRequest,
    KISAuthTokenRemoveResponse,
    KISAuthTokenResponse,
    KISBaseAuthTokenHeader,
    KISWebSocketTokenResponse,
    KISWebSocketTokenRequest,
)


logger = get_logger(__name__)

# 만료 직전 토큰을 꺼내 쓰다 요청 도중 만료되는 것을 막는 여유분(초).
# KIS 토큰 수명은 하루라 10분을 깎아도 재발급 횟수가 늘지 않는다.
TOKEN_TTL_MARGIN_SECONDS = 600


class KISAuth:
    class KISEndpoint(StrEnum):
        AUTH_TOKEN = "/oauth2/tokenP"
        REMOVE_AUTH_TOKEN = "/oauth2/revokeP"
        WEBSOCKET_TOKEN = "/oauth2/Approval"

    def __init__(self, settings: Settings, redis: Redis):
        self.kis_virtual = settings.kis_virtual
        self.app_key = settings.kis_app_key
        self.app_secret = settings.kis_app_secret
        self.rest_domain = settings.kis_rest_domain
        self.websocket_domain = settings.kis_websocket_domain
        self.virtual_rest_domain = settings.kis_virtual_rest_domain
        self.virtual_websocket_domain = settings.kis_virtual_websocket_domain
        self.redis = redis

    @property
    def _token_cache_key(self) -> str:
        """접근 토큰을 담을 Redis 키를 만든다.

        Returns:
            실전/모의 구분과 앱키 해시가 들어간 캐시 키. 앱키를 교체하면 키가
            바뀌어 이전 토큰이 자동으로 버려진다.
        """

        env = "virtual" if self.kis_virtual else "real"
        app_key_digest = hashlib.sha256(self.app_key.encode()).hexdigest()[:12]
        return f"kis:auth:token:{env}:{app_key_digest}"

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
        """캐시된 토큰이 있으면 재사용하고, 없을 때만 새로 발급한다.

        KIS는 토큰 발급을 1분 1회로 제한하므로 발급 결과를 Redis에 담아둔다.
        만료 판정은 Redis TTL이 강제한다.

        Returns:
            캐시에서 꺼냈거나 새로 발급된 access token과 만료 정보를 담은 응답.

        Raises:
            httpx.HTTPStatusError: 인증 요청이 실패한 경우.
            redis.exceptions.RedisError: Redis 조회·저장이 실패한 경우.
        """
        cache_key = self._token_cache_key
        cached = await self.redis.get(cache_key)
        if cached is not None:
            logger.info("kis_auth_token_cache_hit", cache_key=cache_key)
            return KISAuthTokenResponse.model_validate_json(cached)

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
            token = KISAuthTokenResponse(**response.json())

        ttl = int(token.expires_in) - TOKEN_TTL_MARGIN_SECONDS
        if ttl > 0:
            await self.redis.set(cache_key, token.model_dump_json(), ex=ttl)

        logger.info("kis_auth_token_issued", cache_key=cache_key, ttl=ttl)
        return token

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

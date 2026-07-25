"""KIS 국내 투자자 수급 진단 서비스."""

from typing import Protocol, cast

import httpx
from pydantic import JsonValue

from app.core.config import Settings
from app.kis.korea.investor.requests import build_headers, build_requests
from app.kis.korea.investor.schemas import (
    InvestorFlowProbeOptions,
    InvestorFlowResult,
    parse_investor_flow_body,
)
from app.kis.schemas import KISAuthTokenResponse


class _KISRestTokenProvider(Protocol):
    async def get_auth_token(self) -> KISAuthTokenResponse: ...


class KISKoreaInvestorFlowService:
    """실전 KIS 국내 투자자 수급 응답 진단 서비스."""

    def __init__(self, settings: Settings, auth: _KISRestTokenProvider) -> None:
        """진단 서비스 의존성을 초기화한다.

        Args:
            settings: 실전 KIS 도메인과 인증 설정.
            auth: REST 접근 토큰 제공자.
        """

        self.settings = settings
        self.auth = auth

    async def collect_results(
        self,
        options: InvestorFlowProbeOptions,
        client: httpx.AsyncClient,
    ) -> tuple[InvestorFlowResult, ...]:
        """KIS 투자자 수급 API를 순차 호출해 원본 응답을 수집한다.

        Args:
            options: 장중 또는 장 마감 진단 옵션.
            client: 요청에 사용할 비동기 HTTP 클라이언트.

        Returns:
            요청 순서대로 정렬된 응답 결과.

        Raises:
            ValueError: 모의투자 설정으로 실행한 경우.
            httpx.HTTPError: 토큰 발급 또는 네트워크 전송에 실패한 경우.
        """

        if self.settings.kis_virtual:
            raise ValueError("실전키 진단은 KIS_VIRTUAL=false 설정이 필요합니다.")

        token = await self.auth.get_auth_token()
        results: list[InvestorFlowResult] = []
        for request in build_requests(options):
            response = await client.get(
                url=f"{self.settings.kis_rest_domain.rstrip('/')}{request.tr_id.path}",
                headers=build_headers(self.settings, token.access_token, request),
                params=request.params,
            )
            try:
                body = cast(JsonValue, response.json())
            except ValueError:
                body = response.text

            results.append(
                InvestorFlowResult(
                    target=request.target,
                    target_name=request.target_name,
                    venue=request.venue,
                    tr_id=request.tr_id,
                    http_status=response.status_code,
                    tr_cont=response.headers.get("tr_cont", ""),
                    body=parse_investor_flow_body(request.tr_id, body),
                )
            )
        return tuple(results)

"""KIS 국내 투자자 수급 수집 서비스."""

from typing import Protocol, cast

import httpx
from pydantic import JsonValue

from app.core.config import Settings
from app.core.http import raise_for_status
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
    """실전 KIS 국내 투자자 수급 응답 수집 서비스."""

    def __init__(self, settings: Settings, auth: _KISRestTokenProvider) -> None:
        """수집 서비스 의존성을 초기화한다.

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
            options: 장중 또는 장 마감 수집 옵션.
            client: 요청에 사용할 비동기 HTTP 클라이언트.

        Returns:
            요청 순서대로 정렬된 응답 결과.

        Raises:
            ValueError: 모의투자 설정으로 실행한 경우.
            httpx.HTTPError: 토큰 발급·네트워크 전송에 실패하거나 응답이 4xx·5xx인 경우.
        """

        if self.settings.kis_virtual:
            raise ValueError("실전키 수집은 KIS_VIRTUAL=false 설정이 필요합니다.")

        token = await self.auth.get_auth_token()
        results: list[InvestorFlowResult] = []
        for request in build_requests(options):
            response = await client.get(
                url=f"{self.settings.kis_rest_domain.rstrip('/')}{request.tr_id.path}",
                headers=build_headers(
                    self.settings,
                    token.access_token,
                    request,
                ).model_dump(mode="json"),
                params=request.params.model_dump(mode="json"),
            )
            # 5xx·502는 KIS나 게이트웨이의 일시 장애다. 여기서 예외로 올려야
            # Celery가 재시도한다. 그냥 담아두면 rt_cd 검사도 통과하지 못한 채
            # 0행 저장으로 끝나고, 그 시각 데이터는 영영 비어 있는다.
            # rt_cd != "0"(HTTP 200) 업무 오류는 재시도해도 같은 답이라 그대로 담는다.
            raise_for_status(
                response,
                source="kis_investor_flow",
                tr_id=request.tr_id.value,
                target=request.target,
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

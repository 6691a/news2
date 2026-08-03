"""운영 이슈 digest를 구조화된 분석으로 변환한다."""

import json
from collections.abc import Mapping
from typing import Protocol

import httpx
import sentry_sdk
import structlog

from app.notifications.models import (
    AnalysisConfidence,
    AnalysisSource,
    IssueAnalysis,
    IssueDigest,
    IssueKind,
)


logger = structlog.get_logger(__name__)
RESPONSES_URL = "https://api.openai.com/v1/responses"


class IssueAnalyzer(Protocol):
    """Issue digest 분석기의 제공자 독립 계약."""

    async def analyze(self, digest: IssueDigest) -> IssueAnalysis:
        """관측된 digest를 구조화된 분석 결과로 변환한다."""


class OpenAIResponsesIssueAnalyzer:
    """OpenAI Responses API의 Structured Outputs 기반 분석기."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float,
        max_groups: int,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """구성된 HTTP 클라이언트와 모델 설정을 보관한다."""

        self._client = client
        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._max_groups = max_groups

    async def analyze(self, digest: IssueDigest) -> IssueAnalysis:
        """Responses API를 호출하고 응답을 검증된 분석 모델로 반환한다."""

        if self._client is not None:
            return await self._request(self._client, digest)
        async with httpx.AsyncClient() as client:
            return await self._request(client, digest)

    async def _request(self, client: httpx.AsyncClient, digest: IssueDigest) -> IssueAnalysis:
        response = await client.post(
            RESPONSES_URL,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self._model,
                "instructions": _analysis_instructions(),
                "input": _digest_input(digest, max_groups=self._max_groups),
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "issue_analysis",
                        "strict": True,
                        "schema": IssueAnalysis.model_json_schema(),
                    }
                },
                "store": False,
            },
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()
        output_text = _extract_output_text(response.json())
        analysis = IssueAnalysis.model_validate_json(output_text)
        return analysis.model_copy(update={"generated_by": AnalysisSource.LLM})


async def analyze_with_fallback(analyzer: IssueAnalyzer, digest: IssueDigest) -> IssueAnalysis:
    """분석 장애를 격리하고 규칙 기반 결과로 알림 흐름을 계속한다."""

    try:
        return await analyzer.analyze(digest)
    except Exception as exc:
        logger.exception(
            "issue_llm_analysis_failed",
            digest_id=digest.digest_id,
            error_type=type(exc).__name__,
        )
        sentry_sdk.capture_exception(exc)
        return build_fallback_analysis(digest)


def build_fallback_analysis(digest: IssueDigest) -> IssueAnalysis:
    """추정 없이 digest의 관측값만 요약한 낮은 신뢰도 분석을 만든다."""

    high_count = sum(group.count for group in digest.groups if group.severity.value == "high")
    overview = (
        f"{int((digest.window_end - digest.window_start).total_seconds() // 60)}분 동안 "
        f"운영 이슈 {digest.total_events}건이 {len(digest.groups)}개 유형으로 집계되었습니다. "
        f"이 중 높은 심각도 이벤트는 {high_count}건입니다."
    )
    kinds = {group.kind for group in digest.groups}
    impact = _fallback_impact(kinds)

    actions: list[str] = []
    for group in digest.groups:
        action = _fallback_action(group.kind, group.operations[0] if group.operations else "unknown")
        if action not in actions:
            actions.append(action)
        if len(actions) == 5:
            break

    evidence = [
        (
            f"{group.kind.value}: {group.count}건, "
            f"{group.first_observed_at.isoformat()}~{group.last_observed_at.isoformat()}"
        )
        for group in digest.groups[:10]
    ]
    return IssueAnalysis(
        overview=overview,
        likely_causes=[],
        impact=impact,
        recommended_actions=actions,
        confidence=AnalysisConfidence.LOW,
        evidence=evidence,
        generated_by=AnalysisSource.FALLBACK,
    )


def _analysis_instructions() -> str:
    return (
        "당신은 데이터 수집 서비스의 운영 이슈 분석기입니다. 입력 JSON에 명시된 사실만 사용하세요. "
        "원인을 단정하지 말고 likely_causes에는 증거로 뒷받침되는 가능성만 적으세요. "
        "영향 범위를 과장하지 말고, 확인 가능한 조치를 우선순위 순으로 최대 5개 제시하세요. "
        "모든 문장은 한국어로 작성하고 generated_by는 llm으로 설정하세요."
    )


def _digest_input(digest: IssueDigest, *, max_groups: int) -> str:
    groups = [group.model_dump(mode="json") for group in digest.groups[:max_groups]]
    payload = {
        "digest_id": digest.digest_id,
        "window_start": digest.window_start.isoformat(),
        "window_end": digest.window_end.isoformat(),
        "total_events": digest.total_events,
        "total_groups": len(digest.groups),
        "included_groups": len(groups),
        "groups": groups,
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _extract_output_text(payload: object) -> str:
    if not isinstance(payload, Mapping):
        raise ValueError("Responses API response must be an object")
    output = payload.get("output")
    if not isinstance(output, list):
        raise ValueError("Responses API response has no output_text")
    for item in output:
        if not isinstance(item, Mapping):
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, Mapping) and part.get("type") == "output_text":
                text = part.get("text")
                if isinstance(text, str) and text:
                    return text
    raise ValueError("Responses API response has no output_text")


def _fallback_impact(kinds: set[IssueKind]) -> str:
    impacts: list[str] = []
    if IssueKind.EMPTY_RESULT in kinds or IssueKind.SAVE_DROP in kinds:
        impacts.append("일부 데이터가 비어 있거나 저장되지 않아 최신 데이터의 완전성이 낮을 수 있습니다.")
    if IssueKind.RETRY_SCHEDULED in kinds or IssueKind.COLLECTION_LATE in kinds:
        impacts.append("수집 완료 시각이 평소보다 늦어질 수 있습니다.")
    if IssueKind.WEBSOCKET_RECONNECT in kinds:
        impacts.append("실시간 연결 재수립 구간에 데이터 수신 지연이 있었을 수 있습니다.")
    return " ".join(impacts) or "관측된 이벤트만으로 구체적인 사용자 영향을 판단할 수 없습니다."


def _fallback_action(kind: IssueKind, operation: str) -> str:
    actions = {
        IssueKind.RETRY_SCHEDULED: f"{operation} 작업의 재시도 로그와 외부 응답 상태를 확인하세요.",
        IssueKind.EMPTY_RESULT: f"{operation} 결과가 비어 있던 입력 범위와 원본 응답을 확인하세요.",
        IssueKind.SAVE_DROP: f"{operation} 저장 전후 건수와 데이터베이스 오류를 확인하세요.",
        IssueKind.COLLECTION_LATE: f"{operation} 실행 시각과 처리 시간을 기준선과 비교하세요.",
        IssueKind.WEBSOCKET_RECONNECT: f"{operation} 연결 종료 원인과 재연결 간격을 확인하세요.",
    }
    return actions[kind]

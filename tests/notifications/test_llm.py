import json
from datetime import UTC, datetime

import httpx
import pytest

from app.notifications.llm import OpenAIResponsesIssueAnalyzer, analyze_with_fallback, build_fallback_analysis
from app.notifications.models import (
    AnalysisConfidence,
    AnalysisSource,
    IssueAnalysis,
    IssueDigest,
    IssueGroup,
    IssueKind,
    IssueSeverity,
)


def issue_digest() -> IssueDigest:
    return IssueDigest(
        digest_id="3600:1785729600",
        window_start=datetime(2026, 8, 3, 4, 0, tzinfo=UTC),
        window_end=datetime(2026, 8, 3, 5, 0, tzinfo=UTC),
        total_events=3,
        groups=[
            IssueGroup(
                fingerprint="retry_scheduled:celery:ohlcv.collect_overseas_daily",
                kind=IssueKind.RETRY_SCHEDULED,
                severity=IssueSeverity.HIGH,
                count=3,
                first_observed_at=datetime(2026, 8, 3, 4, 5, tzinfo=UTC),
                last_observed_at=datetime(2026, 8, 3, 4, 45, tzinfo=UTC),
                services=["celery"],
                operations=["ohlcv.collect_overseas_daily"],
                contexts=[{"retry_count": 3, "symbol": "AAPL"}],
            )
        ],
    )


def test_fallback_analysis_uses_only_measured_digest_facts() -> None:
    analysis = build_fallback_analysis(issue_digest())

    assert analysis.generated_by is AnalysisSource.FALLBACK
    assert analysis.confidence is AnalysisConfidence.LOW
    assert "3" in analysis.overview
    assert analysis.likely_causes == []
    assert len(analysis.recommended_actions) <= 5
    assert any("retry_scheduled" in evidence for evidence in analysis.evidence)


@pytest.mark.asyncio
async def test_openai_adapter_requests_strict_structured_output() -> None:
    response_analysis = {
        "overview": "한 시간 동안 동일 수집 작업의 재시도가 3회 발생했습니다.",
        "likely_causes": ["외부 데이터 소스의 일시적 응답 지연"],
        "impact": "해외 일봉 데이터 갱신이 지연될 수 있습니다.",
        "recommended_actions": ["외부 소스 응답 시간과 작업 로그를 확인하세요."],
        "confidence": "medium",
        "evidence": ["재시도 3회", "04:05~04:45 UTC"],
        "generated_by": "llm",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-key"
        body = json.loads(request.content)
        assert body["model"] == "configured-model"
        assert body["text"]["format"]["type"] == "json_schema"
        assert body["text"]["format"]["strict"] is True
        assert body["store"] is False
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": json.dumps(response_analysis)}],
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        analyzer = OpenAIResponsesIssueAnalyzer(
            client=client,
            api_key="test-key",
            model="configured-model",
            timeout_seconds=5,
            max_groups=10,
        )
        analysis = await analyzer.analyze(issue_digest())

    assert analysis.generated_by is AnalysisSource.LLM
    assert analysis.confidence is AnalysisConfidence.MEDIUM
    assert analysis.recommended_actions == ["외부 소스 응답 시간과 작업 로그를 확인하세요."]


@pytest.mark.asyncio
async def test_openai_adapter_rejects_missing_output_text() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"output": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        analyzer = OpenAIResponsesIssueAnalyzer(
            client=client,
            api_key="test-key",
            model="configured-model",
            timeout_seconds=5,
            max_groups=10,
        )

        with pytest.raises(ValueError, match="output_text"):
            await analyzer.analyze(issue_digest())


class FailingAnalyzer:
    async def analyze(self, _: IssueDigest) -> IssueAnalysis:
        raise httpx.ReadTimeout("LLM timeout")


@pytest.mark.asyncio
async def test_analysis_failure_returns_fallback_instead_of_blocking_notification() -> None:
    analysis = await analyze_with_fallback(FailingAnalyzer(), issue_digest())

    assert analysis.generated_by is AnalysisSource.FALLBACK
    assert analysis.confidence is AnalysisConfidence.LOW

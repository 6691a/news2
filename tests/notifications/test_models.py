from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.notifications.models import (
    AnalysisConfidence,
    AnalysisSource,
    IndexReportPayload,
    IndexSnapshot,
    IssueAnalysis,
    IssueDigest,
    IssueEvent,
    IssueGroup,
    IssueKind,
    IssueSeverity,
    MarketFlow,
    PriorityCheck,
    ReportPayload,
)


def test_issue_event_requires_timezone_aware_observed_at() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        IssueEvent.create(
            kind=IssueKind.EMPTY_RESULT,
            service="ohlcv",
            operation="collect_korea",
            observed_at=datetime(2026, 8, 3, 4, 0),
        )


def test_issue_event_normalizes_time_and_builds_stable_fingerprint() -> None:
    kst = timezone(timedelta(hours=9))

    event = IssueEvent.create(
        kind=IssueKind.EMPTY_RESULT,
        service="ohlcv",
        operation="collect_korea",
        stable_dimension="daily",
        observed_at=datetime(2026, 8, 3, 13, 0, tzinfo=kst),
    )

    assert event.observed_at == datetime(2026, 8, 3, 4, 0, tzinfo=UTC)
    assert event.fingerprint == "empty_result:ohlcv:collect_korea:daily"


def test_issue_event_context_accepts_scalars_only() -> None:
    with pytest.raises(ValidationError):
        IssueEvent.create(
            kind=IssueKind.RETRY_SCHEDULED,
            service="celery",
            operation="task",
            context={"nested": {"secret": "value"}},
        )


def test_digest_and_analysis_contracts_are_immutable() -> None:
    group = IssueGroup(
        fingerprint="retry_scheduled:celery:task",
        kind=IssueKind.RETRY_SCHEDULED,
        severity=IssueSeverity.WARNING,
        count=2,
        first_observed_at=datetime(2026, 8, 3, 4, 0, tzinfo=UTC),
        last_observed_at=datetime(2026, 8, 3, 4, 30, tzinfo=UTC),
        services=["celery"],
        operations=["task"],
        contexts=[],
    )
    digest = IssueDigest(
        digest_id="issue-20260803T040000Z-3600",
        window_start=datetime(2026, 8, 3, 4, 0, tzinfo=UTC),
        window_end=datetime(2026, 8, 3, 5, 0, tzinfo=UTC),
        total_events=2,
        groups=[group],
    )
    analysis = IssueAnalysis(
        overview="두 차례 재시도됨",
        likely_causes=[],
        impact="수집 지연 가능",
        recommended_actions=["외부 API 상태 확인"],
        confidence=AnalysisConfidence.LOW,
        evidence=["retry_scheduled 2회"],
        generated_by=AnalysisSource.FALLBACK,
    )

    assert digest.groups[0].count == 2
    assert analysis.generated_by is AnalysisSource.FALLBACK
    with pytest.raises(ValidationError):
        digest.total_events = 3


def test_report_payload_limits_executive_summary_to_five_items() -> None:
    with pytest.raises(ValidationError):
        ReportPayload(
            report_id="daily-20260803",
            title="일일 투자 분석",
            as_of=datetime(2026, 8, 3, 6, 30, tzinfo=UTC),
            market_session="한국장 마감",
            executive_summary=[str(index) for index in range(6)],
            disclaimer="투자 권유가 아닙니다.",
        )


def test_report_payload_defaults_priority_checks_to_empty() -> None:
    report = ReportPayload(
        report_id="daily-20260803",
        title="일일 투자 분석",
        as_of=datetime(2026, 8, 3, 6, 30, tzinfo=UTC),
        market_session="한국장 마감",
        disclaimer="투자 권유가 아닙니다.",
    )

    assert report.priority_checks == []


def test_index_report_payload_normalizes_as_of_to_utc() -> None:
    kst = timezone(timedelta(hours=9))

    report = IndexReportPayload(
        report_id="index-20260803",
        title="일일 지수 리포트",
        as_of=datetime(2026, 8, 3, 15, 40, tzinfo=kst),
        market_session="한국장 마감",
        executive_summary=["코스피가 상승했습니다."],
        indices=[
            IndexSnapshot(
                name="KOSPI",
                value="2,768.42",
                change_percent=1.18,
                note="외국인 순매수",
            )
        ],
        priority_checks=[PriorityCheck(title="코스피 2,750선", detail="1차 지지 구간")],
        market_flows=[MarketFlow(title="수급", detail="외국인 +4,280억")],
        disclaimer="투자 권유가 아닙니다.",
    )

    assert report.as_of == datetime(2026, 8, 3, 6, 40, tzinfo=UTC)
    assert report.indices[0].change_percent == 1.18


def test_index_report_payload_rejects_naive_as_of() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        IndexReportPayload(
            report_id="index-20260803",
            title="일일 지수 리포트",
            as_of=datetime(2026, 8, 3, 15, 40),
            market_session="한국장 마감",
            disclaimer="투자 권유가 아닙니다.",
        )


def test_index_snapshot_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        IndexSnapshot.model_validate(
            {
                "name": "KOSPI",
                "value": "2,768.42",
                "change_percent": 1.18,
                "currency": "KRW",
            }
        )


@pytest.mark.parametrize("value", ["", "x" * 501])
def test_index_report_payload_rejects_invalid_list_items(value: str) -> None:
    with pytest.raises(ValidationError):
        IndexReportPayload(
            report_id="index-20260803",
            title="일일 지수 리포트",
            as_of=datetime(2026, 8, 3, 6, 40, tzinfo=UTC),
            market_session="한국장 마감",
            risks=[value],
            disclaimer="투자 권유가 아닙니다.",
        )

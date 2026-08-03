from datetime import UTC, datetime

import pytest

from app.notifications.models import (
    AnalysisConfidence,
    AnalysisSource,
    IndexReportPayload,
    IndexSnapshot,
    IssueAnalysis,
    IssueDigest,
    IssueGroup,
    IssueKind,
    IssueSeverity,
    MarketFlow,
    PriorityCheck,
    ReportDriver,
    ReportPayload,
    SignalSummary,
)
from app.notifications.slack import RenderedMessage
from app.notifications.templates import render_index_report, render_investment_report, render_issue_digest


def block_position(message: RenderedMessage, title: str) -> int:
    expected = f"*{title}*"
    for index, block in enumerate(message.blocks):
        text = block.get("text")
        if not isinstance(text, dict):
            continue
        value = text.get("text")
        if value == expected or (isinstance(value, str) and value.startswith(f"{expected}\n")):
            return index
    raise ValueError(f"section not found: {title}")


def sample_digest() -> IssueDigest:
    group = IssueGroup(
        fingerprint="retry_scheduled:celery:ohlcv.collect_overseas_daily",
        kind=IssueKind.RETRY_SCHEDULED,
        severity=IssueSeverity.HIGH,
        count=2,
        first_observed_at=datetime(2026, 8, 3, 4, 0, tzinfo=UTC),
        last_observed_at=datetime(2026, 8, 3, 4, 30, tzinfo=UTC),
        services=["celery"],
        operations=["ohlcv.collect_overseas_daily"],
        contexts=[{"retry_count": 2, "reason_type": "HTTPStatusError"}],
    )
    return IssueDigest(
        digest_id="issue-20260803T040000Z-3600",
        window_start=datetime(2026, 8, 3, 4, 0, tzinfo=UTC),
        window_end=datetime(2026, 8, 3, 5, 0, tzinfo=UTC),
        total_events=2,
        groups=[group],
    )


def sample_analysis() -> IssueAnalysis:
    return IssueAnalysis(
        overview="해외 일봉 수집이 두 번 재시도되었습니다.",
        likely_causes=["외부 API의 일시 오류"],
        impact="리포트 생성 시각이 늦어질 수 있습니다.",
        recommended_actions=["외부 API 상태를 확인하세요."],
        confidence=AnalysisConfidence.MEDIUM,
        evidence=["retry_scheduled 2회"],
        generated_by=AnalysisSource.LLM,
    )


def test_issue_template_contains_accessible_text_and_analysis_source() -> None:
    message = render_issue_digest(sample_digest(), sample_analysis())

    assert "운영 이슈 요약" in message.text
    assert "issue-20260803T040000Z-3600" in message.text
    assert sample_analysis().impact in message.text
    assert sample_analysis().recommended_actions[0] in message.text
    assert any("분석 요약" in str(block) for block in message.blocks)
    assert any("LLM" in str(block) for block in message.blocks)


def test_issue_template_places_impact_and_actions_before_analysis() -> None:
    message = render_issue_digest(sample_digest(), sample_analysis())

    assert block_position(message, "영향") < block_position(message, "분석 요약")
    assert block_position(message, "우선 조치") < block_position(message, "분석 요약")


def test_issue_template_omits_empty_impact_and_limits_field_text() -> None:
    digest = sample_digest()
    group = digest.groups[0].model_copy(update={"operations": ["x" * 2500]})
    digest = digest.model_copy(update={"groups": [group]})
    analysis = sample_analysis().model_copy(update={"impact": ""})

    message = render_issue_digest(digest, analysis)

    assert all(
        len(field["text"]) <= 2000
        for block in message.blocks
        for field in block.get("fields", [])
        if isinstance(field, dict) and isinstance(field.get("text"), str)
    )
    with pytest.raises(ValueError, match="section not found"):
        block_position(message, "영향")


def test_issue_fallback_text_preserves_digest_id_with_long_action() -> None:
    digest = sample_digest()
    analysis = sample_analysis().model_copy(update={"recommended_actions": ["x" * 5000]})

    message = render_issue_digest(digest, analysis)

    assert digest.digest_id in message.text
    assert "x" * 501 not in message.text


def test_report_template_omits_empty_sections_but_keeps_disclaimer() -> None:
    report = ReportPayload(
        report_id="daily-20260803",
        title="일일 투자 분석",
        as_of=datetime(2026, 8, 3, 6, 30, tzinfo=UTC),
        market_session="한국장 마감",
        executive_summary=["반도체 업종이 상승했습니다."],
        signals=[],
        risks=[],
        disclaimer="검증되지 않은 참고 정보이며 투자 권유가 아닙니다.",
    )

    message = render_investment_report(report)

    rendered = str(message.blocks)
    assert "일일 투자 분석" in message.text
    assert "시그널" not in rendered
    assert "리스크와 확인 사항" not in rendered
    assert report.disclaimer in rendered


def test_report_template_renders_nonempty_signal_section() -> None:
    report = ReportPayload(
        report_id="daily-20260803",
        title="일일 투자 분석",
        as_of=datetime(2026, 8, 3, 6, 30, tzinfo=UTC),
        market_session="한국장 마감",
        signals=[SignalSummary(name="NVDA 모멘텀", state="강화", rationale="거래량 증가")],
        disclaimer="투자 권유가 아닙니다.",
    )

    message = render_investment_report(report)

    assert "시그널" in str(message.blocks)
    assert "NVDA 모멘텀" in str(message.blocks)


def test_investment_report_follows_action_first_section_order() -> None:
    report = ReportPayload(
        report_id="daily-20260803",
        title="일일 투자 분석",
        as_of=datetime(2026, 8, 3, 6, 30, tzinfo=UTC),
        market_session="한국장 마감",
        executive_summary=["반도체 업종이 상승했습니다."],
        priority_checks=[PriorityCheck(title="미국 10년물 금리", detail="성장주 변동성을 확인합니다.")],
        market_drivers=[ReportDriver(title="반도체 수급", direction="개선", rationale="외국인 매수가 유입됐습니다.")],
        disclaimer="투자 권유가 아닙니다.",
    )

    message = render_investment_report(report)

    positions = [
        block_position(message, "오늘의 결론"),
        block_position(message, "우선 확인"),
        block_position(message, "주요 시장 동인"),
    ]
    assert positions == sorted(positions)
    assert report.executive_summary[0] in message.text
    assert report.priority_checks[0].title in message.text


def sample_index_report() -> IndexReportPayload:
    return IndexReportPayload(
        report_id="index-20260803",
        title="일일 지수 리포트",
        as_of=datetime(2026, 8, 3, 6, 40, tzinfo=UTC),
        market_session="한국장 마감",
        executive_summary=["코스피가 상승 마감했습니다."],
        indices=[
            IndexSnapshot(name="KOSPI", value="2,768.42", change_percent=1.18, note="외국인 수급 주도"),
            IndexSnapshot(name="KOSDAQ", value="812.17", change_percent=-0.34, note="바이오 차익실현"),
            IndexSnapshot(name="S&P 500", value="5,547.21", change_percent=0.0, note="전일 종가"),
        ],
        priority_checks=[PriorityCheck(title="코스피 2,750선", detail="1차 지지 구간")],
        market_drivers=[ReportDriver(title="외국인 수급", direction="긍정", rationale="순매수가 상승을 견인했습니다.")],
        market_flows=[
            MarketFlow(title="수급", detail="외국인 +4,280억"),
            MarketFlow(title="기술적 구간", detail="지지 2,750 · 저항 2,800"),
        ],
        next_session_checks=["외국인 반도체 순매수 연속성"],
        risks=["미국 금리 급등 시 지지선 재시험 가능"],
        data_quality_notes=["해외 지수는 전일 종가 기준"],
        disclaimer="이 메시지는 참고 정보이며 투자 권유가 아닙니다.",
    )


def test_index_report_follows_action_first_section_order() -> None:
    message = render_index_report(sample_index_report())

    titles = [
        "오늘의 결론",
        "주요 지수 한눈에 보기",
        "우선 확인",
        "상승·하락 핵심 동인",
        "수급·기술적 구간",
        "다음 장 체크포인트",
        "리스크·데이터 품질",
    ]
    positions = [block_position(message, title) for title in titles]
    assert positions == sorted(positions)


def test_index_report_renders_signed_changes_and_accessible_text() -> None:
    report = sample_index_report()

    message = render_index_report(report)

    rendered = str(message.blocks)
    assert "+1.18%" in rendered
    assert "-0.34%" in rendered
    assert "+0.00%" in rendered
    assert report.report_id in message.text
    assert report.executive_summary[0] in message.text
    assert report.priority_checks[0].title in message.text
    assert report.disclaimer in rendered


def test_index_report_batches_snapshots_into_pairs() -> None:
    message = render_index_report(sample_index_report())

    field_blocks = [block for block in message.blocks if block.get("fields")]

    assert len(field_blocks) == 2
    assert all(len(block["fields"]) <= 2 for block in field_blocks)


def test_index_report_omits_empty_optional_sections() -> None:
    report = IndexReportPayload(
        report_id="index-empty-20260803",
        title="일일 지수 리포트",
        as_of=datetime(2026, 8, 3, 6, 40, tzinfo=UTC),
        market_session="한국장 마감",
        disclaimer="투자 권유가 아닙니다.",
    )

    rendered = str(render_index_report(report).blocks)

    assert "주요 지수 한눈에 보기" not in rendered
    assert "우선 확인" not in rendered
    assert "다음 장 체크포인트" not in rendered

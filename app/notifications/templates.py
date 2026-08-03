"""운영 이슈와 투자 리포트를 Slack Block Kit 메시지로 렌더링."""

from collections.abc import Iterable
from zoneinfo import ZoneInfo

from app.notifications.models import IndexReportPayload, IssueAnalysis, IssueDigest, PriorityCheck, ReportPayload
from app.notifications.slack import RenderedMessage


KST = ZoneInfo("Asia/Seoul")
SECTION_TEXT_LIMIT = 2900


def _truncate(value: str, limit: int = SECTION_TEXT_LIMIT) -> str:
    if len(value) <= limit:
        return value
    shortened = value[: limit - 1].rsplit(" ", 1)[0]
    return f"{shortened or value[: limit - 1]}…"


def _bullets(items: Iterable[str]) -> str:
    return "\n".join(f"• {_truncate(item, 500)}" for item in items)


def _section(title: str, body: str) -> dict[str, object]:
    return {
        "type": "section",
        "text": {"type": "mrkdwn", "text": _truncate(f"*{title}*\n{body}")},
    }


def _priority_checks(items: Iterable[PriorityCheck]) -> str:
    return "\n".join(f"• *{_truncate(item.title, 120)}* — {_truncate(item.detail, 500)}" for item in items)


def _risk_quality(risks: list[str], data_quality_notes: list[str]) -> str:
    parts: list[str] = []
    if risks:
        parts.append(f"*리스크*\n{_bullets(risks)}")
    if data_quality_notes:
        parts.append(f"*데이터 품질*\n{_bullets(data_quality_notes)}")
    return "\n\n".join(parts)


def _fallback_text(*parts: str) -> str:
    return _truncate(" · ".join(part for part in parts if part), 3900)


def render_issue_digest(digest: IssueDigest, analysis: IssueAnalysis) -> RenderedMessage:
    """운영 이슈 digest와 분석을 접근 가능한 Slack 메시지로 만든다."""

    start = digest.window_start.astimezone(KST).strftime("%Y-%m-%d %H:%M")
    end = digest.window_end.astimezone(KST).strftime("%H:%M KST")
    severity = "HIGH" if any(group.severity.value == "high" for group in digest.groups) else "WARNING"
    operations = sorted({operation for group in digest.groups for operation in group.operations})
    groups = [
        f"{index}. `{group.kind.value}` · {group.count}회 · {', '.join(group.operations)}"
        for index, group in enumerate(digest.groups, start=1)
    ]
    cause_text = _bullets(analysis.likely_causes) if analysis.likely_causes else "• 확인된 원인 후보 없음"
    action_text = _bullets(analysis.recommended_actions) or "• 관측 지표와 외부 서비스 상태 확인"
    source = "LLM" if analysis.generated_by.value == "llm" else "fallback"
    text = _fallback_text(
        f"운영 이슈 요약 {start}–{end}: {digest.total_events}건, {len(digest.groups)}개 그룹, 상태 {severity}",
        f"영향: {analysis.impact}" if analysis.impact else "",
        f"우선 조치: {_truncate(analysis.recommended_actions[0], 500)}"
        if analysis.recommended_actions
        else "우선 조치: 관측 지표와 외부 서비스 상태 확인",
        f"Digest ID {digest.digest_id}",
    )
    blocks: list[dict[str, object]] = [
        {"type": "header", "text": {"type": "plain_text", "text": "운영 이슈 요약", "emoji": True}},
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*구간*\n{start}–{end}"},
                {"type": "mrkdwn", "text": f"*상태*\n{severity}"},
                {"type": "mrkdwn", "text": f"*발생*\n{digest.total_events}건 · {len(digest.groups)}개 그룹"},
                {"type": "mrkdwn", "text": _truncate(f"*영향 작업*\n{', '.join(operations)}", 1900)},
            ],
        },
        {"type": "divider"},
    ]
    if analysis.impact:
        blocks.append(_section("영향", analysis.impact))
    blocks.extend(
        [
            _section("우선 조치", action_text),
            _section(
                "분석 요약",
                f"{analysis.overview}\n\n*가능한 원인*\n{cause_text}\n\n신뢰도: *{analysis.confidence.value.upper()}*",
            ),
            _section("주요 관측", "\n".join(groups)),
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": f"분석 방식: *{source}* · Digest ID: `{digest.digest_id}`"}],
            },
        ]
    )
    return RenderedMessage(text=text, blocks=blocks)


def render_investment_report(report: ReportPayload) -> RenderedMessage:
    """투자 분석 입력 계약을 빈 섹션 없는 Slack 메시지로 만든다."""

    as_of = report.as_of.astimezone(KST).strftime("%Y-%m-%d %H:%M KST")
    text = _fallback_text(
        report.title,
        report.market_session,
        as_of,
        f"오늘의 결론: {report.executive_summary[0]}" if report.executive_summary else "",
        f"우선 확인: {report.priority_checks[0].title}" if report.priority_checks else "",
        f"고지: {report.disclaimer}",
        f"Report ID {report.report_id}",
    )
    blocks: list[dict[str, object]] = [
        {"type": "header", "text": {"type": "plain_text", "text": _truncate(report.title, 150), "emoji": True}},
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"{report.market_session} · {as_of}"}],
        },
    ]
    if report.executive_summary:
        blocks.append(_section("오늘의 결론", _bullets(report.executive_summary)))
    if report.priority_checks:
        blocks.append(_section("우선 확인", _priority_checks(report.priority_checks)))
    if report.market_drivers:
        blocks.append(
            _section(
                "주요 시장 동인",
                "\n".join(
                    f"• *{driver.title}* ({driver.direction}) — {driver.rationale}" for driver in report.market_drivers
                ),
            )
        )
    if report.watchlist:
        blocks.append(
            _section(
                "관심 종목",
                "\n".join(
                    f"• *{item.symbol}* ({item.direction}) — {item.rationale}"
                    + (f" / 반대 시나리오: {item.counter_scenario}" if item.counter_scenario else "")
                    for item in report.watchlist
                ),
            )
        )
    if report.signals:
        blocks.append(
            _section(
                "시그널",
                "\n".join(f"• *{signal.name}* [{signal.state}] — {signal.rationale}" for signal in report.signals),
            )
        )
    risk_quality = _risk_quality(report.risks, report.data_quality_notes)
    if risk_quality:
        blocks.append(_section("리스크·데이터 품질", risk_quality))
    if report.sources:
        blocks.append(_section("출처", "\n".join(f"• <{source.url}|{source.label}>" for source in report.sources)))
    blocks.extend(
        [
            {"type": "divider"},
            _section("고지", report.disclaimer),
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": f"Report ID: `{report.report_id}`"}],
            },
        ]
    )
    return RenderedMessage(text=text, blocks=blocks)


def render_index_report(report: IndexReportPayload) -> RenderedMessage:
    """지수 분석 입력 계약을 행동 우선 Slack 메시지로 만든다."""

    as_of = report.as_of.astimezone(KST).strftime("%Y-%m-%d %H:%M KST")
    text = _fallback_text(
        report.title,
        report.market_session,
        as_of,
        f"오늘의 결론: {report.executive_summary[0]}" if report.executive_summary else "",
        f"우선 확인: {report.priority_checks[0].title}" if report.priority_checks else "",
        f"고지: {report.disclaimer}",
        f"Report ID {report.report_id}",
    )
    blocks: list[dict[str, object]] = [
        {"type": "header", "text": {"type": "plain_text", "text": _truncate(report.title, 150), "emoji": True}},
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"{report.market_session} · {as_of}"}],
        },
    ]
    if report.executive_summary:
        blocks.append(_section("오늘의 결론", _bullets(report.executive_summary)))
    if report.indices:
        fields = []
        for item in report.indices:
            note = f"\n{item.note}" if item.note else ""
            fields.append(
                {
                    "type": "mrkdwn",
                    "text": _truncate(
                        f"*{item.name}*\n{item.value} · {item.change_percent:+.2f}%{note}",
                        1800,
                    ),
                }
            )
        for index in range(0, len(fields), 2):
            block: dict[str, object] = {"type": "section", "fields": fields[index : index + 2]}
            if index == 0:
                block["text"] = {"type": "mrkdwn", "text": "*주요 지수 한눈에 보기*"}
            blocks.append(block)
    if report.priority_checks:
        blocks.append(_section("우선 확인", _priority_checks(report.priority_checks)))
    if report.market_drivers:
        blocks.append(
            _section(
                "상승·하락 핵심 동인",
                "\n".join(
                    f"• *{driver.title}* ({driver.direction}) — {driver.rationale}" for driver in report.market_drivers
                ),
            )
        )
    if report.market_flows:
        blocks.append(
            _section(
                "수급·기술적 구간",
                "\n".join(f"• *{flow.title}* — {flow.detail}" for flow in report.market_flows),
            )
        )
    if report.next_session_checks:
        blocks.append(_section("다음 장 체크포인트", _bullets(report.next_session_checks)))
    risk_quality = _risk_quality(report.risks, report.data_quality_notes)
    if risk_quality:
        blocks.append(_section("리스크·데이터 품질", risk_quality))
    if report.sources:
        blocks.append(_section("출처", "\n".join(f"• <{source.url}|{source.label}>" for source in report.sources)))
    blocks.extend(
        [
            {"type": "divider"},
            _section("고지", report.disclaimer),
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": f"Report ID: `{report.report_id}`"}],
            },
        ]
    )
    return RenderedMessage(text=text, blocks=blocks)

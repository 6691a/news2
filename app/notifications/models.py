"""운영 이슈와 투자 리포트가 공유하는 검증된 데이터 계약."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Self, TypeAlias
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


JSONScalar: TypeAlias = str | int | float | bool | None
ReportText: TypeAlias = Annotated[str, Field(min_length=1, max_length=500)]


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC)


class FrozenModel(BaseModel):
    """생성 뒤 변경할 수 없는 공통 Pydantic 모델."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class IssueKind(StrEnum):
    """자동 감지 운영 이상의 종류."""

    RETRY_SCHEDULED = "retry_scheduled"
    EMPTY_RESULT = "empty_result"
    SAVE_DROP = "save_drop"
    COLLECTION_LATE = "collection_late"
    WEBSOCKET_RECONNECT = "websocket_reconnect"


class IssueSeverity(StrEnum):
    """운영 이슈의 상대 심각도."""

    WARNING = "warning"
    HIGH = "high"


class AnalysisConfidence(StrEnum):
    """LLM 또는 fallback 분석의 신뢰 수준."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AnalysisSource(StrEnum):
    """운영 이슈 분석 생성 방식."""

    LLM = "llm"
    FALLBACK = "fallback"


class IssueEvent(FrozenModel):
    """한 번 관측된 자동 운영 이상."""

    event_id: UUID = Field(default_factory=uuid4)
    fingerprint: str = Field(min_length=1, max_length=240)
    kind: IssueKind
    service: str = Field(min_length=1, max_length=100)
    operation: str = Field(min_length=1, max_length=160)
    observed_at: datetime
    severity: IssueSeverity = IssueSeverity.WARNING
    summary: str = Field(default="", max_length=500)
    metric_name: str | None = Field(default=None, max_length=100)
    observed_value: float | int | None = None
    expected_value: float | int | None = None
    correlation_id: str | None = Field(default=None, max_length=200)
    context: dict[str, JSONScalar] = Field(default_factory=dict)

    _normalize_observed_at = field_validator("observed_at")(_aware_utc)

    @classmethod
    def create(
        cls,
        *,
        kind: IssueKind,
        service: str,
        operation: str,
        stable_dimension: str | None = None,
        observed_at: datetime | None = None,
        severity: IssueSeverity = IssueSeverity.WARNING,
        summary: str = "",
        metric_name: str | None = None,
        observed_value: float | int | None = None,
        expected_value: float | int | None = None,
        correlation_id: str | None = None,
        context: dict[str, JSONScalar] | None = None,
    ) -> Self:
        """안정적인 필드만으로 fingerprint를 만들어 이벤트를 생성한다."""

        fingerprint_parts = [kind.value, service, operation]
        if stable_dimension:
            fingerprint_parts.append(stable_dimension)
        return cls(
            fingerprint=":".join(fingerprint_parts),
            kind=kind,
            service=service,
            operation=operation,
            observed_at=observed_at or datetime.now(UTC),
            severity=severity,
            summary=summary,
            metric_name=metric_name,
            observed_value=observed_value,
            expected_value=expected_value,
            correlation_id=correlation_id,
            context=context or {},
        )


class IssueGroup(FrozenModel):
    """같은 fingerprint의 이벤트 집계."""

    fingerprint: str
    kind: IssueKind
    severity: IssueSeverity
    count: int = Field(gt=0)
    first_observed_at: datetime
    last_observed_at: datetime
    services: list[str]
    operations: list[str]
    contexts: list[dict[str, JSONScalar]]

    _normalize_first = field_validator("first_observed_at")(_aware_utc)
    _normalize_last = field_validator("last_observed_at")(_aware_utc)

    @model_validator(mode="after")
    def validate_period(self) -> Self:
        """그룹의 마지막 관측 시각이 최초 관측보다 빠르지 않은지 검증한다."""

        if self.last_observed_at < self.first_observed_at:
            raise ValueError("last_observed_at must not be before first_observed_at")
        return self


class IssueDigest(FrozenModel):
    """완료된 시간 버킷의 운영 이슈 요약."""

    digest_id: str
    window_start: datetime
    window_end: datetime
    total_events: int = Field(gt=0)
    groups: list[IssueGroup] = Field(min_length=1)

    _normalize_start = field_validator("window_start")(_aware_utc)
    _normalize_end = field_validator("window_end")(_aware_utc)

    @model_validator(mode="after")
    def validate_window_and_count(self) -> Self:
        """digest 시간 범위와 그룹별 사건 합계를 검증한다."""

        if self.window_end <= self.window_start:
            raise ValueError("window_end must be after window_start")
        if sum(group.count for group in self.groups) != self.total_events:
            raise ValueError("total_events must equal the sum of group counts")
        return self


class IssueAnalysis(FrozenModel):
    """운영 이슈 digest의 구조화 분석."""

    overview: str = Field(max_length=1500)
    likely_causes: list[str] = Field(max_length=5)
    impact: str = Field(max_length=1500)
    recommended_actions: list[str] = Field(max_length=5)
    confidence: AnalysisConfidence
    evidence: list[str] = Field(max_length=10)
    generated_by: AnalysisSource


class PriorityCheck(FrozenModel):
    """리포트에서 먼저 확인해야 할 항목."""

    title: str = Field(min_length=1, max_length=120)
    detail: str = Field(min_length=1, max_length=500)


class ReportDriver(FrozenModel):
    """시장 방향을 설명하는 주요 동인."""

    title: str = Field(max_length=120)
    direction: str = Field(max_length=40)
    rationale: str = Field(max_length=700)


class InstrumentInsight(FrozenModel):
    """관심 종목별 분석 요약."""

    symbol: str = Field(max_length=32)
    direction: str = Field(max_length=40)
    rationale: str = Field(max_length=700)
    counter_scenario: str = Field(default="", max_length=500)


class SignalSummary(FrozenModel):
    """신규 또는 변경된 투자 시그널."""

    name: str = Field(max_length=120)
    state: str = Field(max_length=40)
    rationale: str = Field(max_length=700)


class SourceLink(FrozenModel):
    """리포트 판단 근거 링크."""

    label: str = Field(max_length=120)
    url: str = Field(max_length=1000)


class IndexSnapshot(FrozenModel):
    """특정 시점의 지수 값과 등락 정보."""

    name: str = Field(min_length=1, max_length=80)
    value: str = Field(min_length=1, max_length=80)
    change_percent: float
    note: str = Field(default="", max_length=300)


class MarketFlow(FrozenModel):
    """지수 리포트의 수급 또는 기술적 구간 요약."""

    title: str = Field(min_length=1, max_length=120)
    detail: str = Field(min_length=1, max_length=700)


class ReportPayload(FrozenModel):
    """향후 투자 분석 파이프라인이 Slack renderer에 넘길 계약."""

    report_id: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=150)
    as_of: datetime
    market_session: str = Field(min_length=1, max_length=100)
    executive_summary: list[ReportText] = Field(default_factory=list, max_length=5)
    priority_checks: list[PriorityCheck] = Field(default_factory=list, max_length=8)
    market_drivers: list[ReportDriver] = Field(default_factory=list, max_length=8)
    watchlist: list[InstrumentInsight] = Field(default_factory=list, max_length=12)
    signals: list[SignalSummary] = Field(default_factory=list, max_length=10)
    risks: list[ReportText] = Field(default_factory=list, max_length=8)
    data_quality_notes: list[ReportText] = Field(default_factory=list, max_length=8)
    sources: list[SourceLink] = Field(default_factory=list, max_length=10)
    disclaimer: str = Field(min_length=1, max_length=1000)

    _normalize_as_of = field_validator("as_of")(_aware_utc)


class IndexReportPayload(FrozenModel):
    """지수 분석 파이프라인이 Slack renderer에 넘길 계약."""

    report_id: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=150)
    as_of: datetime
    market_session: str = Field(min_length=1, max_length=100)
    executive_summary: list[ReportText] = Field(default_factory=list, max_length=5)
    indices: list[IndexSnapshot] = Field(default_factory=list, max_length=8)
    priority_checks: list[PriorityCheck] = Field(default_factory=list, max_length=8)
    market_drivers: list[ReportDriver] = Field(default_factory=list, max_length=8)
    market_flows: list[MarketFlow] = Field(default_factory=list, max_length=8)
    next_session_checks: list[ReportText] = Field(default_factory=list, max_length=8)
    risks: list[ReportText] = Field(default_factory=list, max_length=8)
    data_quality_notes: list[ReportText] = Field(default_factory=list, max_length=8)
    sources: list[SourceLink] = Field(default_factory=list, max_length=10)
    disclaimer: str = Field(min_length=1, max_length=1000)

    _normalize_as_of = field_validator("as_of")(_aware_utc)

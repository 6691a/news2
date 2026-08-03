"""Slack과 LLM으로 나가는 운영 문맥의 허용 목록과 마스킹."""

from collections.abc import Mapping
import re

from app.notifications.models import JSONScalar


FILTERED = "[Filtered]"
SAFE_CONTEXT_KEYS = frozenset(
    {
        "expected",
        "fetched",
        "host",
        "instrument",
        "path",
        "phase",
        "reason_type",
        "retry_count",
        "saved",
        "scope",
        "series",
        "status_code",
    }
)
SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(api_key|app_key|app_secret|authorization|cookie|database_url|openai_api_key|password|redis_url|sentry_dsn|slack_bot_token|token)=([^\s&]+)"
)


def mask_text(value: str) -> str:
    """문자열에 포함된 알려진 자격 증명 할당 값을 마스킹한다."""

    return SECRET_ASSIGNMENT.sub(lambda match: f"{match.group(1)}={FILTERED}", value)


def redact_issue_context(context: Mapping[str, object]) -> dict[str, JSONScalar]:
    """허용된 키와 JSON scalar 값만 운영 이슈 문맥으로 반환한다."""

    redacted: dict[str, JSONScalar] = {}
    for key, value in context.items():
        if key not in SAFE_CONTEXT_KEYS or not isinstance(value, (str, int, float, bool, type(None))):
            continue
        redacted[key] = mask_text(value) if isinstance(value, str) else value
    return redacted

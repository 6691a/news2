from app.notifications.redaction import FILTERED, mask_text, redact_issue_context


def test_redact_issue_context_keeps_only_allowlisted_scalars() -> None:
    redacted = redact_issue_context(
        {
            "series": "US10Y",
            "status_code": 500,
            "saved": 0,
            "api_key": "secret",
            "authorization": "Bearer secret",
            "unknown": "drop-me",
            "nested": {"password": "secret"},
        }
    )

    assert redacted == {"series": "US10Y", "status_code": 500, "saved": 0}


def test_mask_text_filters_query_and_assignment_secrets() -> None:
    text = (
        "request https://api.example.com/data?api_key=secret&series=US10Y "
        "Authorization=Bearer-secret slack_bot_token=xoxb-secret"
    )

    masked = mask_text(text)

    assert "secret" not in masked
    assert "series=US10Y" in masked
    assert masked.count(FILTERED) == 3

import asyncio
from collections.abc import Sequence

import pytest
from slack_sdk.errors import SlackApiError

from app.notifications.slack import RenderedMessage, SlackDeliveryError, SlackGateway


class FakeSlackClient:
    def __init__(self, outcomes: Sequence[object] = ()) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict[str, object]] = []

    async def chat_postMessage(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(kwargs)
        if self.outcomes:
            outcome = self.outcomes.pop(0)
            if isinstance(outcome, BaseException):
                raise outcome
            assert isinstance(outcome, dict)
            return outcome
        return {"ok": True, "channel": kwargs["channel"], "ts": "123.456"}


@pytest.mark.asyncio
async def test_gateway_routes_issue_and_report_to_separate_channels() -> None:
    client = FakeSlackClient()
    gateway = SlackGateway(
        client=client,
        issues_channel_id="CISSUES",
        reports_channel_id="CREPORTS",
        max_attempts=1,
    )
    message = RenderedMessage(text="fallback", blocks=[{"type": "section"}])

    issue_receipt = await gateway.send_issue(message)
    report_receipt = await gateway.send_report(message)

    assert [call["channel"] for call in client.calls] == ["CISSUES", "CREPORTS"]
    assert all(call["text"] == "fallback" and call["blocks"] == message.blocks for call in client.calls)
    assert issue_receipt.channel == "CISSUES"
    assert report_receipt.channel == "CREPORTS"


@pytest.mark.asyncio
async def test_gateway_retries_transient_timeout() -> None:
    client = FakeSlackClient([TimeoutError("temporary"), {"ok": True, "channel": "CISSUES", "ts": "1.0"}])
    gateway = SlackGateway(
        client=client,
        issues_channel_id="CISSUES",
        reports_channel_id="CREPORTS",
        max_attempts=2,
        retry_delay_seconds=0,
    )

    receipt = await gateway.send_issue(RenderedMessage(text="issue", blocks=[]))

    assert receipt.ts == "1.0"
    assert len(client.calls) == 2


@pytest.mark.asyncio
async def test_gateway_does_not_retry_authentication_error() -> None:
    error = SlackApiError("invalid auth", response={"error": "invalid_auth"})  # type: ignore[arg-type]
    client = FakeSlackClient([error])
    gateway = SlackGateway(
        client=client,
        issues_channel_id="CISSUES",
        reports_channel_id="CREPORTS",
        max_attempts=3,
        retry_delay_seconds=0,
    )

    with pytest.raises(SlackDeliveryError, match="invalid_auth"):
        await gateway.send_issue(RenderedMessage(text="issue", blocks=[]))

    assert len(client.calls) == 1


@pytest.mark.asyncio
async def test_gateway_exhausts_transient_retries() -> None:
    client = FakeSlackClient([asyncio.TimeoutError(), asyncio.TimeoutError()])
    gateway = SlackGateway(
        client=client,
        issues_channel_id="CISSUES",
        reports_channel_id="CREPORTS",
        max_attempts=2,
        retry_delay_seconds=0,
    )

    with pytest.raises(SlackDeliveryError, match="TimeoutError"):
        await gateway.send_issue(RenderedMessage(text="issue", blocks=[]))

    assert len(client.calls) == 2

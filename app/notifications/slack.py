"""Slack Web API를 통한 운영 이슈와 투자 리포트 전송."""

import asyncio
from dataclasses import dataclass
from typing import Protocol

from slack_sdk.errors import SlackApiError

from app.core.logging import get_logger


logger = get_logger(__name__)
RETRYABLE_SLACK_ERRORS = frozenset(
    {"fatal_error", "internal_error", "ratelimited", "request_timeout", "service_unavailable"}
)


class AsyncSlackClient(Protocol):
    """Slack SDK 비동기 클라이언트의 사용 범위."""

    async def chat_postMessage(self, **kwargs: object) -> object:
        """채널에 메시지를 전송한다."""


@dataclass(frozen=True, slots=True)
class RenderedMessage:
    """접근성 fallback과 Block Kit 본문."""

    text: str
    blocks: list[dict[str, object]]


@dataclass(frozen=True, slots=True)
class SlackReceipt:
    """성공한 Slack 전송의 최소 식별자."""

    channel: str
    ts: str


class SlackDeliveryError(RuntimeError):
    """Slack 전송이 영구 실패했거나 재시도를 소진한 경우."""


class SlackGateway:
    """논리 메시지를 설정된 Issue 또는 Report 채널로 전송한다."""

    def __init__(
        self,
        *,
        client: AsyncSlackClient,
        issues_channel_id: str,
        reports_channel_id: str,
        max_attempts: int = 3,
        retry_delay_seconds: float = 1.0,
    ) -> None:
        """Slack 클라이언트와 두 대상 채널 및 재시도 정책을 설정한다."""

        if max_attempts <= 0:
            raise ValueError("max_attempts must be positive")
        self.client = client
        self.issues_channel_id = issues_channel_id
        self.reports_channel_id = reports_channel_id
        self.max_attempts = max_attempts
        self.retry_delay_seconds = retry_delay_seconds

    async def send_issue(self, message: RenderedMessage) -> SlackReceipt:
        """운영 이슈 메시지를 Issue 채널로 전송한다."""

        return await self._send(channel=self.issues_channel_id, channel_role="issue", message=message)

    async def send_report(self, message: RenderedMessage) -> SlackReceipt:
        """투자 리포트 메시지를 Report 채널로 전송한다."""

        return await self._send(channel=self.reports_channel_id, channel_role="report", message=message)

    async def _send(
        self,
        *,
        channel: str,
        channel_role: str,
        message: RenderedMessage,
    ) -> SlackReceipt:
        last_error: BaseException | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = await self.client.chat_postMessage(
                    channel=channel,
                    text=message.text,
                    blocks=message.blocks,
                    unfurl_links=False,
                    unfurl_media=False,
                )
                channel_value = str(response["channel"])  # type: ignore[index]
                ts_value = str(response["ts"])  # type: ignore[index]
                logger.info(
                    "slack_message_sent",
                    channel_role=channel_role,
                    attempt=attempt,
                )
                return SlackReceipt(channel=channel_value, ts=ts_value)
            except SlackApiError as error:
                last_error = error
                error_code = str(error.response.get("error", "unknown"))
                if error_code not in RETRYABLE_SLACK_ERRORS or attempt == self.max_attempts:
                    logger.error(
                        "slack_message_failed",
                        channel_role=channel_role,
                        attempt=attempt,
                        error_type=error_code,
                    )
                    raise SlackDeliveryError(error_code) from error
            except (TimeoutError, OSError) as error:
                last_error = error
                if attempt == self.max_attempts:
                    error_type = type(error).__name__
                    logger.error(
                        "slack_message_failed",
                        channel_role=channel_role,
                        attempt=attempt,
                        error_type=error_type,
                    )
                    raise SlackDeliveryError(error_type) from error

            if self.retry_delay_seconds:
                await asyncio.sleep(self.retry_delay_seconds * 2 ** (attempt - 1))

        raise SlackDeliveryError(type(last_error).__name__ if last_error else "unknown")

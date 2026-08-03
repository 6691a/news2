from enum import StrEnum
from typing import Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LogFormat(StrEnum):
    """애플리케이션 로그 출력 형식."""

    CONSOLE = "console"
    JSON = "json"


class LogLevel(StrEnum):
    """애플리케이션에서 허용하는 로그 심각도."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str
    # Celery broker. 호스트 실행은 .env, 컨테이너는 .env.docker가 채운다.
    redis_url: str
    log_format: LogFormat = LogFormat.CONSOLE
    log_level: LogLevel = LogLevel.INFO

    # 오류 추적과 Slack 운영 알림
    sentry_dsn: str = ""
    sentry_environment: str = "local"
    sentry_release: str = ""
    slack_notifications_enabled: bool = False
    slack_bot_token: str = ""
    slack_issues_channel_id: str = ""
    slack_reports_channel_id: str = ""
    issue_digest_interval_seconds: int = 3600
    issue_event_retention_seconds: int = 86400
    issue_llm_provider: str = "openai"
    issue_llm_model: str = ""
    issue_llm_timeout_seconds: float = 30.0
    issue_llm_max_groups: int = 20
    openai_api_key: str = ""

    # 한국투자증권
    kis_virtual: bool = False
    kis_app_key: str
    kis_app_secret: str
    kis_rest_domain: str
    kis_websocket_domain: str
    kis_virtual_rest_domain: str
    kis_virtual_websocket_domain: str

    # FRED(세인트루이스 연은). 미국 국채 확정 수익률 조회에만 쓴다.
    fred_api_key: str

    @model_validator(mode="after")
    def validate_notification_settings(self) -> Self:
        """알림 기능의 교차 설정과 시간 범위를 검증한다.

        Returns:
            검증을 마친 설정 객체.

        Raises:
            ValueError: 지원하지 않는 값이나 활성화에 필요한 값이 빠진 경우.
        """

        if self.issue_llm_provider != "openai":
            raise ValueError("ISSUE_LLM_PROVIDER must be 'openai'")
        if self.issue_digest_interval_seconds <= 0:
            raise ValueError("ISSUE_DIGEST_INTERVAL_SECONDS must be positive")
        if self.issue_event_retention_seconds < max(86_400, 2 * self.issue_digest_interval_seconds):
            raise ValueError(
                "ISSUE_EVENT_RETENTION_SECONDS must be at least max(86400, 2 * ISSUE_DIGEST_INTERVAL_SECONDS)"
            )
        if self.issue_llm_timeout_seconds <= 0:
            raise ValueError("ISSUE_LLM_TIMEOUT_SECONDS must be positive")
        if self.issue_llm_max_groups <= 0:
            raise ValueError("ISSUE_LLM_MAX_GROUPS must be positive")
        if not self.slack_notifications_enabled:
            return self

        required = {
            "SLACK_BOT_TOKEN": self.slack_bot_token,
            "SLACK_ISSUES_CHANNEL_ID": self.slack_issues_channel_id,
            "SLACK_REPORTS_CHANNEL_ID": self.slack_reports_channel_id,
            "ISSUE_LLM_MODEL": self.issue_llm_model,
            "OPENAI_API_KEY": self.openai_api_key,
        }
        for name, value in required.items():
            if not value:
                raise ValueError(f"{name} is required when SLACK_NOTIFICATIONS_ENABLED=true")
        return self


settings = Settings()

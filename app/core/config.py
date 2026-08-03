from enum import StrEnum
from typing import Annotated

from pydantic import Field, HttpUrl, StringConstraints, UrlConstraints
from pydantic_settings import BaseSettings, SettingsConfigDict


NonBlankString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
SentryDsn = Annotated[HttpUrl, UrlConstraints(allowed_schemes=['https'])]
SampleRate = Annotated[float, Field(ge=0.0, le=1.0)]


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

    sentry_dsn: SentryDsn
    sentry_environment: NonBlankString
    sentry_release: NonBlankString
    sentry_traces_sample_rate: SampleRate = 0.1
    sentry_error_sample_rate: SampleRate = 1.0

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


settings = Settings()

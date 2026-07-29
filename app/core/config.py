from enum import StrEnum

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

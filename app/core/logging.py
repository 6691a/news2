"""structlog 기반 애플리케이션 로깅을 구성한다."""

import logging
import sys
from typing import cast

import structlog
from structlog.types import Processor

from app.core.config import LogFormat, Settings


def _without_query(value: object) -> object:
    """URL 문자열이면 쿼리 문자열을 떼고, 아니면 원본을 그대로 돌려준다.

    Args:
        value: 로그 레코드의 인자 하나.

    Returns:
        `http://host/path` 형태로 자른 문자열 또는 원본 값.
    """

    text = str(value)
    if not text.startswith(("http://", "https://")) or "?" not in text:
        return value
    return text.split("?", 1)[0]


class RedactUrlQuery(logging.Filter):
    """외부 HTTP 클라이언트 로그에서 URL 쿼리 문자열을 지운다.

    쿼리에 API 키가 실리는 소스가 있어(FRED `api_key`) 전체 URL을 남기면 비밀값이
    로그에 들어간다. host와 path만 남겨 요청 대상은 계속 추적할 수 있게 한다.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """레코드 인자에서 URL 쿼리를 제거한다.

        Args:
            record: 검사할 로그 레코드.

        Returns:
            항상 True. 레코드를 버리지 않고 값만 고친다.
        """

        if isinstance(record.args, tuple):
            record.args = tuple(_without_query(argument) for argument in record.args)
        return True


def configure_logging(settings: Settings) -> None:
    """설정에 따라 structlog와 외부 라이브러리 로그 출력을 통합한다.

    Args:
        settings: 로그 레벨과 출력 형식을 포함한 애플리케이션 설정.
    """
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]
    renderer: Processor
    if settings.log_format is LogFormat.JSON:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=[
            structlog.stdlib.ExtraAdder(),
            *shared_processors,
        ],
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            renderer,
        ],
    )
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(settings.log_level.value)

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        external_logger = logging.getLogger(logger_name)
        external_logger.handlers.clear()
        external_logger.propagate = True

    # httpx는 요청 성공을 INFO로 남기면서 전체 URL을 찍는다. FRED처럼 API 키가 쿼리에
    # 실리는 소스가 있어 그대로 두면 비밀값이 로그 파일에 남는다.
    for logger_name in ("httpx", "httpcore"):
        logging.getLogger(logger_name).addFilter(RedactUrlQuery())

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """이름이 지정된 structlog 로거를 반환한다.

    Args:
        name: 로그에 기록할 모듈 또는 컴포넌트 이름.

    Returns:
        표준 로깅 전송 계층에 연결된 structlog bound logger.
    """
    return cast(structlog.stdlib.BoundLogger, structlog.stdlib.get_logger(name))

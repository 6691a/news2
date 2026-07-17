"""structlog 기반 애플리케이션 로깅을 구성한다."""

import logging
import sys
from typing import cast

import structlog
from structlog.types import Processor

from app.core.config import LogFormat, Settings


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

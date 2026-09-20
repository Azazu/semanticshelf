"""Structured logging: structlog for the application, the same renderer for stdlib loggers.

One JSON object per line on stdout by default; a coloured console renderer
when `LOG_JSON=false`. Records written while a request is handled carry the
request id, method and path bound by `RequestIdMiddleware` through
`structlog.contextvars`, which also survives `run_in_threadpool` calls.
"""

import logging
import sys

import structlog
from structlog.typing import Processor

# Loggers whose handlers are replaced so their output goes through the same
# renderer as the application's own records.
_FOREIGN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access", "sqlalchemy", "alembic")


def configure_logging(level: str, json: bool) -> None:
    """Configure structlog and the stdlib root logger. Safe to call more than once."""
    shared: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
        structlog.processors.StackInfoRenderer(),
    ]
    renderer: Processor
    formatter_processors: list[Processor] = [
        structlog.stdlib.ProcessorFormatter.remove_processors_meta
    ]
    if json:
        # Turn `exc_info` into an `exception` string; the console renderer does this itself.
        formatter_processors.append(structlog.processors.format_exc_info)
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()
    formatter_processors.append(renderer)

    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared, processors=formatter_processors
        )
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
    for name in _FOREIGN_LOGGERS:
        foreign = logging.getLogger(name)
        foreign.handlers.clear()
        foreign.propagate = True

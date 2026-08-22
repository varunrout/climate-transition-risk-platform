"""Structured logging setup.

Every pipeline stage logs at minimum: run_id, stage, source (when applicable),
country (when applicable), duration_s, row_count, quality_status.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog


def configure_logging(*, level: int = logging.INFO, json_output: bool = True) -> None:
    """Configure structlog + stdlib logging for the whole process.

    Call once at process entry (CLI command, job entrypoint). Safe to call
    multiple times; later calls simply reconfigure.
    """
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
    ]

    renderer: Any
    if json_output:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[*shared_processors, structlog.processors.format_exc_info, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


def get_logger(**initial_context: Any) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger bound with the given initial context."""
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(**initial_context)
    return logger

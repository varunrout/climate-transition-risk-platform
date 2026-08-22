"""Structured logging setup.

Every pipeline stage logs at minimum: run_id, stage, source (when applicable),
country (when applicable), duration_s, row_count, quality_status.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

import structlog


def _default_level() -> int:
    """INFO unless CLIMATE_RISK_LOG_LEVEL says otherwise.

    Production (Container Apps Job) sets CLIMATE_RISK_LOG_LEVEL=INFO
    explicitly (see infra/modules/container_apps) so this is never left to
    an implicit default in the deployed environment; local runs get the
    same INFO default without needing to set anything. No DEBUG-level
    telemetry is ever enabled by default -- opt in explicitly for local
    debugging only.
    """
    name = os.environ.get("CLIMATE_RISK_LOG_LEVEL", "INFO").upper()
    return logging.getLevelNamesMapping().get(name, logging.INFO)


def configure_logging(*, level: int | None = None, json_output: bool = True) -> None:
    """Configure structlog + stdlib logging for the whole process.

    Call once at process entry (CLI command, job entrypoint). Safe to call
    multiple times; later calls simply reconfigure. `level` defaults to
    `_default_level()` (CLIMATE_RISK_LOG_LEVEL env var, else INFO).
    """
    level = level if level is not None else _default_level()
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

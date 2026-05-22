"""Structured logging setup built on :mod:`structlog`.

`configure_logging()` is called once at startup. Everywhere else just do::

    from app.logging import get_logger
    log = get_logger(__name__)
"""

from __future__ import annotations

import logging
import sys

import structlog

_CONFIGURED = False


def configure_logging(*, level: str = "INFO", json_output: bool = True) -> None:
    """Configure stdlib logging and structlog with a shared processor chain."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    log_level = getattr(logging, level.upper(), logging.INFO)

    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)
    # NB: no `add_logger_name` — it reads `logger.name`, which the lightweight
    # PrintLogger has not. The logger name is bound explicitly in get_logger().
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.StackInfoRenderer(),
        timestamper,
    ]

    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer()
        if json_output
        else structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
    )

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )

    # Route stdlib logging (aiogram, sqlalchemy, apscheduler) through structlog.
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                renderer,
            ],
        )
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(log_level)

    # Tame noisy third-party loggers.
    for noisy in ("aiogram.event", "apscheduler.executors", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(max(log_level, logging.WARNING))

    _CONFIGURED = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger.

    The module name is bound as the ``logger`` field so it appears in every
    log line — done explicitly because the PrintLogger factory has no concept
    of a logger name.

    NB: ``.bind()`` realizes the logger eagerly, so :func:`configure_logging`
    must run *before* any module-level ``get_logger`` call. Entry points
    (``app.__main__``, ``app.cli``) configure logging before importing the
    rest of the application for exactly this reason.
    """
    if name:
        # `.bind()` (not get_logger(logger=...)): `logger` is a reserved
        # keyword of structlog's get_logger() and would collide.
        return structlog.get_logger().bind(logger=name)
    return structlog.get_logger()

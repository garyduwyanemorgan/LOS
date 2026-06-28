"""Structured logging via structlog.

Features:
- JSON output in production, coloured console in development.
- Auto-injected fields: timestamp, level, service, environment.
- Context variables: correlation_id, lagoon_id, request_id (set per-request).
- performance_timer() context manager for measuring code blocks.
- get_logger(name) factory that binds the module name automatically.
"""

from __future__ import annotations

import logging
import sys
import time
from contextlib import contextmanager

# ─── Context variables ────────────────────────────────────────────────────────
# These are set by FastAPI middleware and available throughout a request.
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from collections.abc import Generator

    from structlog.types import EventDict, Processor

_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)
_lagoon_id: ContextVar[str | None] = ContextVar("lagoon_id", default=None)
_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_user_id: ContextVar[str | None] = ContextVar("user_id", default=None)


def set_correlation_id(value: str) -> None:
    _correlation_id.set(value)


def set_lagoon_id(value: str) -> None:
    _lagoon_id.set(value)


def set_request_id(value: str) -> None:
    _request_id.set(value)


def set_user_id(value: str) -> None:
    _user_id.set(value)


# ─── Custom processors ────────────────────────────────────────────────────────

def _inject_context_vars(logger: Any, method: str, event_dict: EventDict) -> EventDict:
    """Inject per-request context variables into every log record."""
    if (cid := _correlation_id.get()) is not None:
        event_dict["correlation_id"] = cid
    if (lid := _lagoon_id.get()) is not None:
        event_dict["lagoon_id"] = lid
    if (rid := _request_id.get()) is not None:
        event_dict["request_id"] = rid
    if (uid := _user_id.get()) is not None:
        event_dict["user_id"] = uid
    return event_dict


def _add_service_info(logger: Any, method: str, event_dict: EventDict) -> EventDict:
    """Add static service metadata to every log record."""
    from backend.core.config.settings import settings

    event_dict.setdefault("service", "los-api")
    event_dict.setdefault("version", settings.APP_VERSION)
    event_dict.setdefault("environment", settings.ENVIRONMENT)
    return event_dict


def _rename_event_key(logger: Any, method: str, event_dict: EventDict) -> EventDict:
    """Rename structlog's 'event' key to 'message' for ELK/Datadog compatibility."""
    if "event" in event_dict:
        event_dict["message"] = event_dict.pop("event")
    return event_dict


# ─── Configuration ────────────────────────────────────────────────────────────

_configured = False


def configure_logging(debug: bool = False, json_format: bool = True) -> None:
    """Configure structlog + stdlib logging.

    Call once at application startup.  Subsequent calls are no-ops.
    """
    global _configured
    if _configured:
        return
    _configured = True

    log_level = logging.DEBUG if debug else logging.INFO

    # Shared processors run on every log record regardless of renderer.
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        _inject_context_vars,
        _add_service_info,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.ExceptionRenderer(),
    ]

    if json_format:
        renderer: Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True, exception_formatter=structlog.dev.plain_traceback)

    structlog.configure(
        processors=[
            *shared_processors,
            # Bridge to stdlib so that third-party loggers (uvicorn, sqlalchemy)
            # also go through structlog's pipeline.
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            _rename_event_key,
            renderer,
        ],
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)

    # Quieten noisy third-party loggers.
    for noisy in ("uvicorn.access", "sqlalchemy.engine", "httpcore", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


# ─── Public factory ───────────────────────────────────────────────────────────

def get_logger(name: str, **initial_values: Any) -> structlog.stdlib.BoundLogger:
    """Return a structlog BoundLogger pre-bound with the module name.

    Usage::

        log = get_logger(__name__)
        log.info("Model run complete", model="FloPy", duration_s=4.2)
    """
    return structlog.get_logger(name, **initial_values)


# ─── Performance timing ───────────────────────────────────────────────────────

@contextmanager
def performance_timer(
    logger: structlog.stdlib.BoundLogger,
    operation: str,
    **extra: Any,
) -> Generator[None, None, None]:
    """Context manager that logs operation timing.

    Usage::

        with performance_timer(log, "modflow-run", lagoon_id=str(lid)):
            result = await run_modflow(...)
    """
    start = time.perf_counter()
    logger.debug("operation-start", operation=operation, **extra)
    try:
        yield
    except Exception as exc:
        elapsed = time.perf_counter() - start
        logger.error(
            "operation-failed",
            operation=operation,
            duration_ms=round(elapsed * 1000, 2),
            error=str(exc),
            **extra,
        )
        raise
    else:
        elapsed = time.perf_counter() - start
        logger.info(
            "operation-complete",
            operation=operation,
            duration_ms=round(elapsed * 1000, 2),
            **extra,
        )

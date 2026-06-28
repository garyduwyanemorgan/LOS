"""Structured logging package — exposes get_logger factory."""

from backend.core.logging.logger import configure_logging, get_logger, performance_timer

__all__ = ["configure_logging", "get_logger", "performance_timer"]

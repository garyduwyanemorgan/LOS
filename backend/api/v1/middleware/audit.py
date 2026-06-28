"""Audit log middleware — records all state-changing API calls.

Every POST, PUT, PATCH, DELETE request is logged to an audit table
with: user ID, method, path, status code, request body (truncated),
and duration.
"""
from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING, Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

logger = logging.getLogger(__name__)

AUDITED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
MAX_BODY_SIZE = 4096  # bytes stored in audit log

# Paths to exclude (e.g., health checks don't need audit)
EXCLUDED_PATHS = {"/health", "/health/ready", "/health/detailed", "/metrics"}


class AuditMiddleware(BaseHTTPMiddleware):
    """Write an audit record for every mutating HTTP request."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method not in AUDITED_METHODS:
            return await call_next(request)

        # Skip excluded paths
        path = request.url.path
        if any(path.endswith(excl) for excl in EXCLUDED_PATHS):
            return await call_next(request)

        start_time = time.monotonic()

        # Read body for audit (may be empty)
        body_bytes = await request.body()
        body_preview = _truncate_body(body_bytes)

        # Restore body so downstream handlers can read it
        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": body_bytes, "more_body": False}

        request._receive = receive  # type: ignore[attr-defined]

        # Extract auth info
        user_id: str | None = None
        user_email: str | None = None
        try:
            user = getattr(request.state, "user", None)
            if user:
                user_id = str(user.get("id", ""))
                user_email = user.get("email", "")
        except Exception:
            pass

        response = await call_next(request)

        duration_ms = round((time.monotonic() - start_time) * 1000, 1)
        request_id = getattr(request.state, "request_id", None)

        audit_record = {
            "request_id": request_id,
            "user_id": user_id,
            "user_email": user_email,
            "method": request.method,
            "path": path,
            "query_string": str(request.query_params),
            "status_code": response.status_code,
            "duration_ms": duration_ms,
            "ip_address": _get_client_ip(request),
            "user_agent": request.headers.get("user-agent", ""),
            "body_preview": body_preview,
        }

        # Log to structured logger (pipeline to DB or SIEM via log shipping)
        logger.info("AUDIT %s %s %d %.1fms", request.method, path, response.status_code, duration_ms, extra={"audit": audit_record})

        # Async write to audit table (fire-and-forget)
        _write_audit_async(audit_record)

        return response


def _truncate_body(body: bytes) -> str:
    """Return a UTF-8 string of the body, truncated to MAX_BODY_SIZE."""
    if not body:
        return ""
    try:
        text = body[:MAX_BODY_SIZE].decode("utf-8", errors="replace")
        if len(body) > MAX_BODY_SIZE:
            text += f"... [{len(body) - MAX_BODY_SIZE} bytes truncated]"
        return text
    except Exception:
        return f"<binary {len(body)} bytes>"


def _get_client_ip(request: Request) -> str:
    """Extract real client IP, respecting X-Forwarded-For if present."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _write_audit_async(record: dict[str, Any]) -> None:
    """Fire-and-forget coroutine to persist audit record.

    Uses the asyncio event loop if available; swallows errors silently
    to avoid disrupting the request/response cycle.
    """
    import asyncio

    async def _write() -> None:
        try:
            # In a real deployment this would use a DB connection from the app's pool
            # For now, emit to a dedicated audit logger that ships to the SIEM
            audit_logger = logging.getLogger("los.audit")
            audit_logger.info(json.dumps(record, default=str))
        except Exception as exc:
            logger.debug("Audit write failed (non-fatal): %s", exc)

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            _task = asyncio.ensure_future(_write())
            _task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
    except RuntimeError:
        pass

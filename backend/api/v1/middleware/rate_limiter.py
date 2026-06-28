"""Sliding-window rate limiter middleware.

Limits are enforced per authenticated user (by JWT subject claim)
or per remote IP for unauthenticated requests.  Redis counters are
used when available; if Redis is unreachable the middleware passes
all requests through rather than rejecting legitimate traffic.

Limits (requests per window):
  Authentication endpoints (/api/v1/auth/*)  : 20 / 60 s
  Report generation (POST …/reports)         : 10 / 60 s
  All other API endpoints                    : 200 / 60 s
"""
from __future__ import annotations

import logging
import time
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request  # noqa: TC002 — used at runtime in dispatch signature
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

# (path_prefix, method_filter, limit, window_seconds)
# Rules are evaluated first-match wins.
_RULES: list[tuple[str, str | None, int, int]] = [
    ("/api/v1/auth/",   None,   20,  60),
    ("/api/v1/",        "POST", 200, 60),  # report generation handled below
    ("/api/v1/",        None,   200, 60),
]
_REPORT_POST_LIMIT = 10
_DEFAULT_LIMIT      = 200
_DEFAULT_WINDOW     = 60  # seconds


def _get_limit(path: str, method: str) -> tuple[int, int]:
    """Return (limit, window_seconds) for this request."""
    if path.startswith("/api/v1/auth/"):
        return 20, 60
    if method == "POST" and "/reports" in path:
        return _REPORT_POST_LIMIT, _DEFAULT_WINDOW
    return _DEFAULT_LIMIT, _DEFAULT_WINDOW


def _extract_key(request: Request) -> str:
    """Derive a rate-limit key: user subject from JWT or remote IP."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            import base64
            import json

            # Decode payload without verification — only for key extraction.
            parts = token.split(".")
            if len(parts) == 3:
                padded = parts[1] + "=" * (-len(parts[1]) % 4)
                payload = json.loads(base64.urlsafe_b64decode(padded))
                sub = payload.get("sub") or payload.get("user_id")
                if sub:
                    return f"rl:user:{sub}"
        except Exception:
            pass

    ip = "unknown"
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    elif request.client:
        ip = request.client.host
    return f"rl:ip:{ip}"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Redis sliding-window rate limiter.

    Degrades gracefully: if Redis is unavailable, all requests pass through.
    """

    _redis: Any = None
    _redis_checked: bool = False

    async def _get_redis(self) -> Any:
        if not self._redis_checked:
            self._redis_checked = True
            try:
                import redis.asyncio as aioredis

                from backend.core.config.settings import settings

                self._redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
                await self._redis.ping()
                logger.info("rate-limiter-redis-connected")
            except Exception as exc:
                logger.warning("rate-limiter-redis-unavailable: %s — rate limiting disabled", exc)
                self._redis = None
        return self._redis

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path

        # Skip health probes and metrics — never rate-limit these.
        if path in {"/health", "/ready", "/metrics"}:
            return await call_next(request)

        redis = await self._get_redis()
        if redis is None:
            return await call_next(request)

        limit, window = _get_limit(path, request.method)
        key = _extract_key(request)
        bucket_key = f"{key}:{int(time.time()) // window}"

        try:
            pipe = redis.pipeline()
            pipe.incr(bucket_key)
            pipe.expire(bucket_key, window * 2)
            results = await pipe.execute()
            count: int = results[0]
        except Exception as exc:
            logger.debug("rate-limiter-redis-error: %s", exc)
            return await call_next(request)

        remaining = max(0, limit - count)
        reset_at = (int(time.time()) // window + 1) * window

        if count > limit:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate-limit-exceeded",
                    "message": "Too many requests. Please slow down.",
                    "retry_after": reset_at - int(time.time()),
                },
                headers={
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_at),
                    "Retry-After": str(reset_at - int(time.time())),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_at)
        return response

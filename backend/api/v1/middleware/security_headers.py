"""Security headers middleware for the Lagoons Operating System API.

Adds security-relevant HTTP response headers to every response to
protect against common web vulnerabilities.
"""

from __future__ import annotations

from typing import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Inject security headers into every HTTP response.

    Headers applied:
    - X-Content-Type-Options: prevent MIME-sniffing attacks
    - X-Frame-Options: prevent clickjacking
    - X-XSS-Protection: legacy XSS filter (belt-and-suspenders)
    - Strict-Transport-Security: enforce HTTPS (HSTS)
    - Referrer-Policy: limit referrer information leakage
    - Permissions-Policy: disable unused browser features
    - Content-Security-Policy: restrict resource loading origins
    - Cache-Control: prevent caching of API responses
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        self._apply_headers(response)
        return response

    @staticmethod
    def _apply_headers(response: Response) -> None:
        # Prevent MIME-type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Prevent embedding in iframes (clickjacking)
        response.headers["X-Frame-Options"] = "DENY"

        # Legacy XSS filter for older browsers
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Enforce HTTPS for 1 year; include subdomains
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )

        # Limit referrer information sent to other origins
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Disable browser features not used by the API
        response.headers["Permissions-Policy"] = (
            "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
            "magnetometer=(), microphone=(), payment=(), usb=()"
        )

        # CSP: API responses are JSON; restrict to self only
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; frame-ancestors 'none'"
        )

        # Do not cache API responses (authentication and live data)
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
        response.headers["Pragma"] = "no-cache"

        # Remove server fingerprinting headers if present
        if "Server" in response.headers:
            del response.headers["Server"]
        if "X-Powered-By" in response.headers:
            del response.headers["X-Powered-By"]

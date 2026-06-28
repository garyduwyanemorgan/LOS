"""Request ID middleware — attaches a unique X-Request-ID to every request."""
from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a UUID request ID to every incoming request.

    - If the client sends an `X-Request-ID` header, that value is used.
    - Otherwise a new UUID4 is generated.
    - The ID is echoed back in the response header.
    - The ID is injected into the logging context for structured log correlation.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())

        # Store on request state so downstream code can read it
        request.state.request_id = request_id

        # Add to structlog context if structlog is available
        try:
            import structlog

            structlog.contextvars.clear_contextvars()
            structlog.contextvars.bind_contextvars(request_id=request_id)
        except ImportError:
            pass

        # Also inject into Python logging via a LoggerAdapter trick
        old_factory = logging.getLogRecordFactory()

        def record_factory(*args, **kwargs):  # type: ignore[no-untyped-def]
            record = old_factory(*args, **kwargs)
            record.request_id = request_id  # type: ignore[attr-defined]
            return record

        logging.setLogRecordFactory(record_factory)

        try:
            response: Response = await call_next(request)
        finally:
            logging.setLogRecordFactory(old_factory)

        response.headers[REQUEST_ID_HEADER] = request_id
        return response

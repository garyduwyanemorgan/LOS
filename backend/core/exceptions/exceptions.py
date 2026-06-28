"""Complete exception hierarchy for the Lagoons Operating System.

Every exception carries:
- message: human-readable description
- error_code: machine-readable kebab-case string for API clients
- detail: optional dict with context (IDs, field names, etc.)
- http_status_code: corresponding HTTP status
"""

from __future__ import annotations

from typing import Any


class LOSException(Exception):
    """Root exception for all LOS errors.

    All application exceptions should inherit from this class so that
    FastAPI exception handlers can provide consistent JSON error responses.
    """

    message: str = "An unexpected error occurred in the Lagoons Operating System."
    error_code: str = "los-error"
    http_status_code: int = 500

    def __init__(
        self,
        message: str | None = None,
        error_code: str | None = None,
        detail: dict[str, Any] | None = None,
        http_status_code: int | None = None,
    ) -> None:
        self.message = message or self.__class__.message
        self.error_code = error_code or self.__class__.error_code
        self.detail: dict[str, Any] = detail or {}
        self.http_status_code = http_status_code or self.__class__.http_status_code
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-safe dict suitable for FastAPI error responses."""
        return {
            "error": self.error_code,
            "message": self.message,
            "detail": self.detail,
        }

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"error_code={self.error_code!r}, "
            f"message={self.message!r}, "
            f"detail={self.detail!r})"
        )


# ─── Infrastructure / data layer ─────────────────────────────────────────────

class DatabaseException(LOSException):
    """Raised when a database operation fails (connection, query, constraint)."""

    message = "A database error occurred."
    error_code = "database-error"
    http_status_code = 503


class EventBusException(LOSException):
    """Raised when publishing to or consuming from the Redis event bus fails."""

    message = "Event bus operation failed."
    error_code = "event-bus-error"
    http_status_code = 503


class SharedMemoryException(LOSException):
    """Raised when a shared memory (Redis / PostgreSQL) read/write fails."""

    message = "Shared memory operation failed."
    error_code = "shared-memory-error"
    http_status_code = 503


# ─── Scientific layers ────────────────────────────────────────────────────────

class ScientificModelException(LOSException):
    """Raised when a scientific model (FloPy, HYDRUS, PHREEQC, etc.) fails.

    Typical causes: missing executable, bad input parameters, solver divergence.
    """

    message = "Scientific model execution failed."
    error_code = "scientific-model-error"
    http_status_code = 422


class ScientificServiceException(LOSException):
    """Raised when a scientific service (Hydrological, Chemical, Ecological,
    Infrastructure loop) encounters a non-recoverable error during analysis."""

    message = "Scientific service encountered an error."
    error_code = "scientific-service-error"
    http_status_code = 500


class DecisionEngineException(LOSException):
    """Raised when the decision engine fails to synthesise recommendations."""

    message = "Decision engine failed to process inputs."
    error_code = "decision-engine-error"
    http_status_code = 500


class SRGException(LOSException):
    """Raised when the Scientific Relationship Graph (Neo4j) operation fails."""

    message = "Scientific Relationship Graph operation failed."
    error_code = "srg-error"
    http_status_code = 503


class SimulationException(LOSException):
    """Raised when a simulation run fails (invalid parameters, timeout, etc.)."""

    message = "Simulation run failed."
    error_code = "simulation-error"
    http_status_code = 422


# ─── Auth ─────────────────────────────────────────────────────────────────────

class AuthenticationException(LOSException):
    """Raised when a request cannot be authenticated (missing/invalid/expired token)."""

    message = "Authentication failed. Please provide a valid token."
    error_code = "authentication-error"
    http_status_code = 401


class AuthorizationException(LOSException):
    """Raised when an authenticated user lacks the required permission."""

    message = "You do not have permission to perform this action."
    error_code = "authorization-error"
    http_status_code = 403


# ─── Validation / resource ───────────────────────────────────────────────────

class ValidationException(LOSException):
    """Raised when request data fails business-logic validation.

    Note: Pydantic schema errors are handled separately by FastAPI and
    produce HTTP 422; this exception is for domain-specific validation
    that Pydantic cannot express (e.g. cross-field rules, DB uniqueness).
    """

    message = "Request data failed validation."
    error_code = "validation-error"
    http_status_code = 422

    def __init__(
        self,
        message: str | None = None,
        field: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        resolved_detail = detail or {}
        if field:
            resolved_detail.setdefault("field", field)
        super().__init__(
            message=message,
            error_code="validation-error",
            detail=resolved_detail,
            http_status_code=422,
        )


class ResourceNotFoundException(LOSException):
    """Raised when a requested resource does not exist in the database."""

    message = "The requested resource was not found."
    error_code = "resource-not-found"
    http_status_code = 404

    def __init__(
        self,
        resource_type: str | None = None,
        resource_id: str | None = None,
        message: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        resolved_detail = detail or {}
        if resource_type:
            resolved_detail["resource_type"] = resource_type
        if resource_id:
            resolved_detail["resource_id"] = resource_id
        resolved_message = message or (
            f"{resource_type} with id '{resource_id}' not found."
            if resource_type and resource_id
            else self.__class__.message
        )
        super().__init__(
            message=resolved_message,
            error_code="resource-not-found",
            detail=resolved_detail,
            http_status_code=404,
        )

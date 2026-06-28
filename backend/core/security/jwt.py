"""JWT utilities for Supabase token validation and LOS-internal token creation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from jose import ExpiredSignatureError, JWTError, jwt

from backend.core.config.settings import settings
from backend.core.exceptions.exceptions import AuthenticationException
from backend.core.logging.logger import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Token payload schemas
# ---------------------------------------------------------------------------

class TokenPayload:
    """Parsed, validated token payload."""

    def __init__(
        self,
        sub: str,
        email: str | None,
        role: str | None,
        org_id: str | None,
        exp: int,
        iat: int,
        jti: str | None = None,
    ) -> None:
        self.sub = sub
        self.email = email
        self.role = role
        self.org_id = org_id
        self.exp = exp
        self.iat = iat
        self.jti = jti

    @property
    def user_id(self) -> str:
        return self.sub

    @property
    def is_expired(self) -> bool:
        return datetime.now(tz=UTC).timestamp() > self.exp

    def to_dict(self) -> dict[str, Any]:
        return {
            "sub": self.sub,
            "email": self.email,
            "role": self.role,
            "org_id": self.org_id,
            "exp": self.exp,
            "iat": self.iat,
            "jti": self.jti,
        }


# ---------------------------------------------------------------------------
# Supabase token validation
# ---------------------------------------------------------------------------

def decode_supabase_token(token: str) -> TokenPayload:
    """Validate and decode a Supabase-issued JWT.

    Supabase signs JWTs with the project's JWT secret (HS256).
    The token's 'sub' claim is the Supabase user UUID.

    Args:
        token: Raw Bearer token string (without "Bearer " prefix).

    Returns:
        Parsed TokenPayload.

    Raises:
        AuthenticationException: If the token is invalid, expired, or cannot
            be decoded.
    """
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            options={"verify_aud": False},  # Supabase does not always set aud
        )
    except ExpiredSignatureError as exc:
        raise AuthenticationException(
            message="Supabase token has expired.",
            detail={"hint": "Refresh your session via the Supabase auth SDK."},
        ) from exc
    except JWTError as exc:
        log.warning("supabase-token-decode-failed", error=str(exc))
        raise AuthenticationException(
            message="Invalid Supabase token.",
            detail={"reason": str(exc)},
        ) from exc

    sub = payload.get("sub")
    if not sub:
        raise AuthenticationException(
            message="Supabase token missing 'sub' claim.",
        )

    # Supabase stores the user's email in the 'email' claim directly.
    return TokenPayload(
        sub=sub,
        email=payload.get("email"),
        role=payload.get("role") or payload.get("user_metadata", {}).get("los_role"),
        org_id=payload.get("app_metadata", {}).get("org_id"),
        exp=int(payload.get("exp", 0)),
        iat=int(payload.get("iat", 0)),
        jti=payload.get("jti"),
    )


# ---------------------------------------------------------------------------
# LOS-internal token creation
# ---------------------------------------------------------------------------

def create_los_token(
    user_id: str,
    email: str,
    role: str,
    org_id: str,
    token_type: str = "access",
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Create a LOS-internal JWT for service-to-service or session use.

    Args:
        user_id: UUID of the LOS user.
        email: User's email address.
        role: LOS Role value (e.g. "ADMIN").
        org_id: Organisation UUID.
        token_type: "access" (short-lived) or "refresh" (long-lived).
        extra_claims: Additional claims to embed.

    Returns:
        Signed JWT string.
    """
    now = datetime.now(tz=UTC)

    if token_type == "refresh":
        expire = now + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    else:
        expire = now + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)

    payload: dict[str, Any] = {
        "sub": user_id,
        "email": email,
        "role": role,
        "org_id": org_id,
        "token_type": token_type,
        "iat": now,
        "exp": expire,
        "jti": str(uuid.uuid4()),
        "iss": "lagoons-operating-system",
    }

    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


# ---------------------------------------------------------------------------
# Generic token validation
# ---------------------------------------------------------------------------

def validate_token(token: str, expected_token_type: str = "access") -> TokenPayload:
    """Validate a LOS-internal JWT.

    Args:
        token: Raw JWT string.
        expected_token_type: "access" or "refresh".

    Returns:
        Parsed TokenPayload.

    Raises:
        AuthenticationException: If validation fails for any reason.
    """
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except ExpiredSignatureError as exc:
        raise AuthenticationException(
            message="Access token has expired.",
            detail={"hint": "Request a new token using your refresh token."},
        ) from exc
    except JWTError as exc:
        log.warning("los-token-validation-failed", error=str(exc))
        raise AuthenticationException(
            message="Invalid LOS access token.",
            detail={"reason": str(exc)},
        ) from exc

    token_type = payload.get("token_type")
    if token_type != expected_token_type:
        raise AuthenticationException(
            message=f"Expected a {expected_token_type!r} token, got {token_type!r}.",
            detail={"expected": expected_token_type, "received": token_type},
        )

    sub = payload.get("sub")
    if not sub:
        raise AuthenticationException(message="Token missing 'sub' claim.")

    return TokenPayload(
        sub=sub,
        email=payload.get("email"),
        role=payload.get("role"),
        org_id=payload.get("org_id"),
        exp=int(payload.get("exp", 0)),
        iat=int(payload.get("iat", 0)),
        jti=payload.get("jti"),
    )

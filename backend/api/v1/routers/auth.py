"""Authentication endpoints — login, logout, token refresh, profile."""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from jose import jwt

from backend.api.v1.schemas import TokenResponse, UserResponse
from backend.core.config.settings import settings

if TYPE_CHECKING:
    from fastapi.security import OAuth2PasswordRequestForm

    from backend.api.v1.dependencies import CurrentUserDep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _create_token(subject: str, expires_delta: timedelta, token_type: str = "access") -> str:
    """Create a signed JWT."""
    expire = datetime.now(UTC) + expires_delta
    payload = {
        "sub": subject,
        "type": token_type,
        "exp": expire,
        "iat": datetime.now(UTC),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


@router.post("/login", response_model=TokenResponse, summary="Authenticate and receive tokens")
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> TokenResponse:
    """Authenticate via email/password through Supabase and return JWTs.

    The access token expires in `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`.
    The refresh token expires in `JWT_REFRESH_TOKEN_EXPIRE_DAYS`.
    """
    try:
        from supabase import create_client  # type: ignore[import]

        supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
        auth_response = supabase.auth.sign_in_with_password(
            {"email": form.username, "password": form.password}
        )
        if auth_response.user is None:
            raise ValueError("Invalid credentials")

        user_id = str(auth_response.user.id)
    except Exception as exc:
        logger.warning("Login failed for %s: %s", form.username, exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    access_token = _create_token(
        user_id,
        timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES),
        "access",
    )
    refresh_token = _create_token(
        user_id,
        timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
        "refresh",
    )

    logger.info("User logged in: %s", form.username)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Invalidate session")
async def logout(current_user: CurrentUserDep) -> None:
    """Invalidate the current user's Supabase session.

    The LOS JWT is stateless so the client must discard the token.
    """
    try:
        from supabase import create_client  # type: ignore[import]

        supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
        supabase.auth.sign_out()
    except Exception as exc:
        logger.warning("Logout Supabase call failed: %s", exc)
        # Still return 204 — client should discard tokens regardless

    logger.info("User logged out: %s", current_user.get("email"))


@router.post("/refresh", response_model=TokenResponse, summary="Refresh access token")
async def refresh_token(refresh_token: str) -> TokenResponse:
    """Exchange a valid refresh token for a new access token."""
    from jose import JWTError

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            refresh_token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        if payload.get("type") != "refresh":
            raise credentials_exception
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError as exc:
        raise credentials_exception from exc

    new_access = _create_token(
        user_id,
        timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES),
        "access",
    )
    new_refresh = _create_token(
        user_id,
        timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
        "refresh",
    )

    return TokenResponse(
        access_token=new_access,
        refresh_token=new_refresh,
        token_type="bearer",
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.get("/profile", response_model=UserResponse, summary="Get current user profile")
async def get_profile(current_user: CurrentUserDep) -> UserResponse:
    """Return the authenticated user's profile."""
    return UserResponse(**current_user)

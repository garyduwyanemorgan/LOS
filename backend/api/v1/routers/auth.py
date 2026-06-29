"""Authentication endpoints — login, logout, token refresh, profile."""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import bcrypt
from fastapi import APIRouter, HTTPException, status
from jose import jwt

from backend.api.v1.dependencies import CurrentUserDep, DatabaseDep
from backend.api.v1.schemas import LoginRequest, TokenResponse, UserResponse
from backend.core.config.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _create_token(subject: str, expires_delta: timedelta, token_type: str = "access") -> str:
    expire = datetime.now(UTC) + expires_delta
    payload = {
        "sub": subject,
        "type": token_type,
        "exp": expire,
        "iat": datetime.now(UTC),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


@router.post("/login", response_model=TokenResponse, summary="Authenticate and receive tokens")
async def login(body: LoginRequest, db: DatabaseDep) -> TokenResponse:
    """Authenticate via email/password against local DB and return JWTs."""
    from backend.database.repositories.user_repo import UserRepository

    repo = UserRepository(db)
    user = await repo.get_by_email_for_auth(body.email)

    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect email or password",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if user is None:
        logger.warning("Login failed — no user found for %s", body.email)
        raise credentials_exc

    hashed = user.get("hashed_password") or ""
    if not hashed:
        logger.warning("Login failed — no password set for %s", body.email)
        raise credentials_exc

    try:
        password_ok = bcrypt.checkpw(body.password.encode(), hashed.encode())
    except Exception as exc:
        logger.error("bcrypt error for %s: %s", body.email, exc)
        password_ok = False

    if not password_ok:
        logger.warning("Login failed — wrong password for %s", body.email)
        raise credentials_exc

    if not user.get("is_active", True):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")

    user_id = str(user["id"])
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

    logger.info("User logged in: %s", body.email)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Invalidate session")
async def logout(current_user: CurrentUserDep) -> None:
    """Invalidate the current user's session. Client must discard the JWT."""
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

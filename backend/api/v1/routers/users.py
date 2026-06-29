"""User management endpoints with role-based access control."""
from __future__ import annotations

import logging
from uuid import UUID

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Path, status

from backend.api.v1.dependencies import (
    CurrentUserDep,
    DatabaseDep,
    PaginationDep,
    require_role,
)
from backend.api.v1.schemas import (
    PaginatedUsers,
    PaginationMeta,
    PasswordChangeRequest,
    UserCreate,
    UserResponse,
    UserUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("", response_model=PaginatedUsers, summary="List users (admin only)")
async def list_users(
    pagination: PaginationDep = ...,
    db: DatabaseDep = ...,
    _: dict = Depends(require_role("admin")),
) -> PaginatedUsers:
    from backend.database.repositories.user_repo import UserRepository  # type: ignore[import]

    repo = UserRepository(db)
    users = await repo.list(skip=pagination.skip, limit=pagination.limit)
    return PaginatedUsers(
        items=[UserResponse(**u) for u in users],
        meta=PaginationMeta(skip=pagination.skip, limit=pagination.limit, total=len(users)),
    )


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a user (admin only)",
)
async def create_user(
    body: UserCreate,
    db: DatabaseDep = ...,
    _: dict = Depends(require_role("admin")),
) -> UserResponse:
    """Create a new user account. Admin-only operation.

    Password is hashed before storage; plain text is never persisted.
    """
    from backend.database.repositories.user_repo import UserRepository  # type: ignore[import]

    repo = UserRepository(db)

    # Check email uniqueness
    existing = await repo.get_by_email(body.email)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"User with email '{body.email}' already exists",
        )

    hashed_password = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt()).decode()

    record = {
        **body.model_dump(exclude={"password"}),
        "hashed_password": hashed_password,
        "is_active": True,
    }
    created = await repo.create(record)
    return UserResponse(**created)


@router.get("/me", response_model=UserResponse, summary="Get current user profile")
async def get_me(current_user: CurrentUserDep = ...) -> UserResponse:
    """Return the profile of the currently authenticated user."""
    return UserResponse(**current_user)


@router.get("/{user_id}", response_model=UserResponse, summary="Get user details")
async def get_user(
    user_id: UUID = Path(...),
    current_user: CurrentUserDep = ...,
    db: DatabaseDep = ...,
) -> UserResponse:
    """Return user details. Users can view their own profile; admins can view any."""
    is_self = str(current_user["id"]) == str(user_id)
    is_admin = current_user.get("role") == "admin"
    if not is_self and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only view your own profile.",
        )

    from backend.database.repositories.user_repo import UserRepository  # type: ignore[import]

    repo = UserRepository(db)
    user = await repo.get(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserResponse(**user)


@router.patch("/{user_id}", response_model=UserResponse, summary="Update user")
async def update_user(
    body: UserUpdate,
    user_id: UUID = Path(...),
    current_user: CurrentUserDep = ...,
    db: DatabaseDep = ...,
) -> UserResponse:
    """Update user fields. Admins can update any user; users can update their own name."""
    is_self = str(current_user["id"]) == str(user_id)
    is_admin = current_user.get("role") == "admin"

    if not is_self and not is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    # Non-admins cannot change their own role
    if not is_admin and body.role is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can change user roles.",
        )

    from backend.database.repositories.user_repo import UserRepository  # type: ignore[import]

    repo = UserRepository(db)
    updated = await repo.update(user_id, body.model_dump(exclude_none=True))
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserResponse(**updated)


@router.post("/{user_id}/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    body: PasswordChangeRequest,
    user_id: UUID = Path(...),
    current_user: CurrentUserDep = ...,
    db: DatabaseDep = ...,
) -> None:
    """Change a user's password. Users can only change their own password."""
    if str(current_user["id"]) != str(user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    from backend.database.repositories.user_repo import UserRepository  # type: ignore[import]

    repo = UserRepository(db)
    user = await repo.get_with_password(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    existing_hash = (user.get("hashed_password") or "").encode()
    if not existing_hash or not bcrypt.checkpw(body.current_password.encode(), existing_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect",
        )

    new_hash = bcrypt.hashpw(body.new_password.encode(), bcrypt.gensalt()).decode()
    await repo.update(user_id, {"hashed_password": new_hash})


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Deactivate user (admin only)",
)
async def deactivate_user(
    user_id: UUID = Path(...),
    current_user: CurrentUserDep = ...,
    db: DatabaseDep = ...,
    _: dict = Depends(require_role("admin")),
) -> None:
    """Deactivate a user account. Admins cannot deactivate themselves."""
    if str(current_user["id"]) == str(user_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot deactivate your own account.",
        )

    from backend.database.repositories.user_repo import UserRepository  # type: ignore[import]

    repo = UserRepository(db)
    success = await repo.update(user_id, {"is_active": False})
    if success is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

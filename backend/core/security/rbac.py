"""Role-Based Access Control for the Lagoons Operating System.

Roles are hierarchical:  SUPERADMIN > ADMIN > ENGINEER ≈ SCIENTIST > OPERATOR > VIEWER
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache

from backend.core.exceptions.exceptions import AuthorizationException


class Role(StrEnum):
    """User roles, ordered from most to least privileged."""

    SUPERADMIN = "SUPERADMIN"
    ADMIN = "ADMIN"
    ENGINEER = "ENGINEER"
    SCIENTIST = "SCIENTIST"
    OPERATOR = "OPERATOR"
    VIEWER = "VIEWER"


class Permission(StrEnum):
    """Granular permissions checked throughout the API."""

    # Lagoon data
    READ_LAGOON = "READ_LAGOON"
    WRITE_LAGOON = "WRITE_LAGOON"
    DELETE_LAGOON = "DELETE_LAGOON"
    CONFIGURE_LAGOON = "CONFIGURE_LAGOON"

    # Sensors
    MANAGE_SENSORS = "MANAGE_SENSORS"

    # Observations
    SUBMIT_OBSERVATION = "SUBMIT_OBSERVATION"

    # Recommendations & interventions
    APPROVE_RECOMMENDATION = "APPROVE_RECOMMENDATION"
    REJECT_RECOMMENDATION = "REJECT_RECOMMENDATION"

    # Simulations
    RUN_SIMULATION = "RUN_SIMULATION"

    # User management
    MANAGE_USERS = "MANAGE_USERS"

    # Reports
    VIEW_REPORTS = "VIEW_REPORTS"
    GENERATE_REPORTS = "GENERATE_REPORTS"

    # Admin
    VIEW_ADMIN = "VIEW_ADMIN"
    MANAGE_SYSTEM = "MANAGE_SYSTEM"


# ---------------------------------------------------------------------------
# Role → Permission mapping
# ---------------------------------------------------------------------------
# Sets are used internally; the public API exposes frozensets for safety.

_ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.VIEWER: {
        Permission.READ_LAGOON,
        Permission.VIEW_REPORTS,
    },
    Role.OPERATOR: {
        Permission.READ_LAGOON,
        Permission.SUBMIT_OBSERVATION,
        Permission.VIEW_REPORTS,
        Permission.APPROVE_RECOMMENDATION,
        Permission.REJECT_RECOMMENDATION,
    },
    Role.SCIENTIST: {
        Permission.READ_LAGOON,
        Permission.WRITE_LAGOON,
        Permission.SUBMIT_OBSERVATION,
        Permission.RUN_SIMULATION,
        Permission.VIEW_REPORTS,
        Permission.GENERATE_REPORTS,
    },
    Role.ENGINEER: {
        Permission.READ_LAGOON,
        Permission.WRITE_LAGOON,
        Permission.CONFIGURE_LAGOON,
        Permission.MANAGE_SENSORS,
        Permission.SUBMIT_OBSERVATION,
        Permission.APPROVE_RECOMMENDATION,
        Permission.REJECT_RECOMMENDATION,
        Permission.RUN_SIMULATION,
        Permission.VIEW_REPORTS,
        Permission.GENERATE_REPORTS,
    },
    Role.ADMIN: {
        Permission.READ_LAGOON,
        Permission.WRITE_LAGOON,
        Permission.DELETE_LAGOON,
        Permission.CONFIGURE_LAGOON,
        Permission.MANAGE_SENSORS,
        Permission.SUBMIT_OBSERVATION,
        Permission.APPROVE_RECOMMENDATION,
        Permission.REJECT_RECOMMENDATION,
        Permission.RUN_SIMULATION,
        Permission.MANAGE_USERS,
        Permission.VIEW_REPORTS,
        Permission.GENERATE_REPORTS,
        Permission.VIEW_ADMIN,
    },
    Role.SUPERADMIN: set(Permission),  # all permissions
}

# Public read-only view.
ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    role: frozenset(perms) for role, perms in _ROLE_PERMISSIONS.items()
}


@lru_cache(maxsize=512)
def _get_permissions(role: Role) -> frozenset[Permission]:
    return ROLE_PERMISSIONS.get(role, frozenset())


def check_permission(role: Role, permission: Permission) -> bool:
    """Return True if *role* has *permission*, False otherwise.

    This is a pure predicate — it does NOT raise an exception.
    """
    return permission in _get_permissions(role)


def require_permission(role: Role, permission: Permission) -> None:
    """Assert that *role* has *permission*.

    Raises:
        AuthorizationException: if the role lacks the required permission.
    """
    if not check_permission(role, permission):
        raise AuthorizationException(
            message=(
                f"Role '{role.value}' does not have the '{permission.value}' permission."
            ),
            detail={
                "role": role.value,
                "required_permission": permission.value,
                "granted_permissions": sorted(
                    p.value for p in _get_permissions(role)
                ),
            },
        )


def get_role_permissions(role: Role) -> list[str]:
    """Return a sorted list of permission values granted to *role*."""
    return sorted(p.value for p in _get_permissions(role))

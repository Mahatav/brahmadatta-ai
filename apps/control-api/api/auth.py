"""Operator authentication and role authorization.

Bearer tokens, one per role, supplied by the environment
(`docs/03-technical/22-authentication-and-authorization-plan.md`). Deliberately
simple: one named operator, one machine, a fourteen-day project. What it is not, is
open by default —

* no configured token means no principal can authenticate, for any role;
* comparison is constant-time;
* an unknown or malformed `Authorization` header is a 401, never an anonymous pass;
* tokens are never logged and never echoed in a response.

Session and MFA-backed administrator auth is out of scope for the seven-day build and
is recorded as a risk on the D1 PR rather than half-implemented here.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from django.conf import settings
from django.http import HttpRequest
from ninja.security import HttpBearer

from contracts.enums import ErrorCode, Role
from contracts.errors import ContractError


@dataclass(frozen=True)
class Principal:
    """The authenticated caller. Carries a role, never the token."""

    role: Role

    def has_any(self, *roles: Role) -> bool:
        return self.role in roles


class ForbiddenError(ContractError):
    code = ErrorCode.FORBIDDEN
    http_status = 403
    default_message = "This role may not perform that action."


class BearerTokenAuth(HttpBearer):
    """`Authorization: Bearer <token>` → `Principal`, or None → 401."""

    def authenticate(self, request: HttpRequest, token: str) -> Principal | None:
        configured: dict[str, str] = getattr(settings, "CONTROL_API_TOKENS", {})
        if not token or not configured:
            return None

        matched: Role | None = None
        # Compare against every configured token rather than short-circuiting, so the
        # response time does not reveal which roles are configured.
        for role_name, expected in configured.items():
            if secrets.compare_digest(token, expected):
                matched = Role(role_name)
        if matched is None:
            return None

        request.principal = Principal(role=matched)
        return request.principal


def require_role(request: HttpRequest, *roles: Role) -> Principal:
    """Authorize before any business logic runs. Raises `ForbiddenError` on refusal."""
    principal: Principal | None = getattr(request, "auth", None) or getattr(
        request, "principal", None
    )
    if principal is None:
        raise ForbiddenError("No authenticated principal on the request.")
    if not principal.has_any(*roles):
        raise ForbiddenError(
            f"Role {principal.role} may not perform that action.",
            details={"required_roles": sorted(str(role) for role in roles)},
        )
    return principal


#: Roles per operation family, from the authorization plan.
OPERATOR_ROLES = (Role.OPERATOR, Role.ADMINISTRATOR)
READ_ROLES = (Role.OPERATOR, Role.REVIEWER, Role.ADMINISTRATOR)
ADMIN_ROLES = (Role.ADMINISTRATOR,)

"""RBAC policy for NikTiar Sovereign Edge unified on-box portal.

One login origin serves both SOC engineers and customer dashboard users.
Customers must never reach admin/SOC operations routes; engineers get full access.

This module is the contract enforced by tests today and by on-appliance API
gateway middleware when the unified portal ships on Sovereign Edge clusters.
See docs/KB112_SOVEREIGN_EDGE_TEST_PLAN.md §5.
"""

from __future__ import annotations

from typing import FrozenSet, Iterable, Optional, Tuple

# SOC engineer personas on the unified appliance (same as cloud admin/SOC roles).
SOC_ENGINEER_ROLES: FrozenSet[str] = frozenset(
    {
        "platform_admin",
        "soc_manager",
        "soc_analyst",
    }
)

# Customer dashboard personas — view alerts, incidents, limited approvals only.
CUSTOMER_DASHBOARD_ROLES: FrozenSet[str] = frozenset(
    {
        "customer_admin",
        "customer_viewer",
    }
)

# Route prefixes a customer must never access on the unified portal.
FORBIDDEN_CUSTOMER_ROUTE_PREFIXES: Tuple[str, ...] = (
    "/admin",
    "/v1/admin",
    "/api/v1/admin",
    "/internal",
    "/appliance-mgmt",
    "/soc-sync",
    "/proxy",
)

# Customer-safe dashboard prefixes (read + scoped write such as isolation approval).
ALLOWED_CUSTOMER_ROUTE_PREFIXES: Tuple[str, ...] = (
    "/auth",
    "/health",
    "/customer",
    "/api/v1/customer",
    "/v1/customer",
)

# Customer may POST/PUT/PATCH only under these prefixes (approval workflows).
CUSTOMER_WRITE_ROUTE_PREFIXES: Tuple[str, ...] = (
    "/customer",
    "/api/v1/customer",
    "/v1/customer",
)

# Explicit customer write subpaths (isolation approval, service requests, etc.).
CUSTOMER_WRITE_PATH_FRAGMENTS: Tuple[str, ...] = (
    "/approve",
    "/approval",
    "/service-requests",
    "/isolation",
)


def normalize_http_method(method: Optional[str]) -> str:
    return (method or "GET").strip().upper()


def normalize_route_path(path: Optional[str]) -> str:
    text = (path or "/").strip()
    if not text.startswith("/"):
        text = f"/{text}"
    # Drop query string if a full URL was passed.
    text = text.split("?", 1)[0]
    if len(text) > 1 and text.endswith("/"):
        text = text.rstrip("/")
    return text or "/"


def is_soc_engineer_role(role: Optional[str]) -> bool:
    return (role or "").strip().lower() in SOC_ENGINEER_ROLES


def is_customer_dashboard_role(role: Optional[str]) -> bool:
    return (role or "").strip().lower() in CUSTOMER_DASHBOARD_ROLES


def path_starts_with_any(path: str, prefixes: Iterable[str]) -> bool:
    for prefix in prefixes:
        if path == prefix or path.startswith(f"{prefix}/"):
            return True
    return False


def sovereign_customer_forbidden_path(path: str) -> bool:
    """True when a customer role must be denied this path on the unified portal."""
    normalized = normalize_route_path(path)
    return path_starts_with_any(normalized, FORBIDDEN_CUSTOMER_ROUTE_PREFIXES)


def sovereign_customer_allowed_path(path: str) -> bool:
    """True when path is in the customer dashboard surface."""
    normalized = normalize_route_path(path)
    if sovereign_customer_forbidden_path(normalized):
        return False
    return path_starts_with_any(normalized, ALLOWED_CUSTOMER_ROUTE_PREFIXES)


def sovereign_customer_may_write(method: str, path: str) -> bool:
    """Customers may only mutate under customer routes and approval fragments."""
    verb = normalize_http_method(method)
    if verb in ("GET", "HEAD", "OPTIONS"):
        return True
    normalized = normalize_route_path(path)
    if not path_starts_with_any(normalized, CUSTOMER_WRITE_ROUTE_PREFIXES):
        return False
    if verb in ("POST", "PUT", "PATCH", "DELETE"):
        return any(fragment in normalized for fragment in CUSTOMER_WRITE_PATH_FRAGMENTS)
    return False


def sovereign_route_access(
    role: Optional[str],
    method: str,
    path: str,
) -> Tuple[bool, Optional[str]]:
    """
    Return (allowed, deny_reason).

    deny_reason is one of: forbidden_admin_route, customer_write_denied, unknown_role.
    """
    normalized_role = (role or "").strip().lower()
    normalized_path = normalize_route_path(path)
    verb = normalize_http_method(method)

    if is_soc_engineer_role(normalized_role):
        return True, None

    if not is_customer_dashboard_role(normalized_role):
        return False, "unknown_role"

    if sovereign_customer_forbidden_path(normalized_path):
        return False, "forbidden_admin_route"

    if not sovereign_customer_allowed_path(normalized_path):
        return False, "forbidden_admin_route"

    if verb in ("GET", "HEAD", "OPTIONS"):
        return True, None

    if sovereign_customer_may_write(verb, normalized_path):
        return True, None

    return False, "customer_write_denied"


def sovereign_http_status_for_deny(reason: Optional[str]) -> int:
    """Map policy deny reason to HTTP status for unified portal gateway."""
    if reason == "forbidden_admin_route":
        return 403
    if reason == "customer_write_denied":
        return 403
    if reason == "unknown_role":
        return 403
    return 403

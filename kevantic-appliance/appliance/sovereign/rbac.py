"""RBAC policy for NikTiar Sovereign Edge unified on-box portal (appliance copy).

Keep in sync with backend-api/app/services/sovereign_rbac.py — parity tested in CI.
"""

from __future__ import annotations

from typing import FrozenSet, Iterable, Optional, Tuple

SOC_ENGINEER_ROLES: FrozenSet[str] = frozenset(
    {
        "platform_admin",
        "soc_manager",
        "soc_analyst",
    }
)

CUSTOMER_DASHBOARD_ROLES: FrozenSet[str] = frozenset(
    {
        "customer_admin",
        "customer_viewer",
    }
)

FORBIDDEN_CUSTOMER_ROUTE_PREFIXES: Tuple[str, ...] = (
    "/admin",
    "/v1/admin",
    "/api/v1/admin",
    "/internal",
    "/appliance-mgmt",
    "/soc-sync",
    "/proxy",
)

ALLOWED_CUSTOMER_ROUTE_PREFIXES: Tuple[str, ...] = (
    "/auth",
    "/health",
    "/customer",
    "/api/v1/customer",
    "/v1/customer",
    "/portal",
    "/",
)

CUSTOMER_WRITE_ROUTE_PREFIXES: Tuple[str, ...] = (
    "/customer",
    "/api/v1/customer",
    "/v1/customer",
)

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
    normalized = normalize_route_path(path)
    return path_starts_with_any(normalized, FORBIDDEN_CUSTOMER_ROUTE_PREFIXES)


def sovereign_customer_allowed_path(path: str) -> bool:
    normalized = normalize_route_path(path)
    if sovereign_customer_forbidden_path(normalized):
        return False
    return path_starts_with_any(normalized, ALLOWED_CUSTOMER_ROUTE_PREFIXES)


def sovereign_customer_may_write(method: str, path: str) -> bool:
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
    return 403

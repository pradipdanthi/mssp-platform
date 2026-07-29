#!/usr/bin/env python3
"""
End-to-end delegated customer user management validation (KB-088 / Gemini spec).

Requires: running stack on localhost:8000, docker postgres, platform admin in DB.
Uses env: PLATFORM_ADMIN_EMAIL, PLATFORM_ADMIN_PASSWORD (defaults match lab scripts).

Temporary tenants named "User Mgmt Test …" are removed on exit (success or failure).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

API = os.environ.get("MSSP_API_BASE", "http://localhost:8000").rstrip("/")
PLATFORM_EMAIL = os.environ.get("PLATFORM_ADMIN_EMAIL", "platform.admin@example.local")
PLATFORM_PASS = os.environ.get("PLATFORM_ADMIN_PASSWORD", "TempPass123!")

# Never remove production/lab customers (case-insensitive short_code prefixes).
_PROTECTED_TENANT_SHORT_PREFIXES = ("ALPHAWIN", "BETALINUX", "ALPHA-WIN")
_VALIDATION_NAME_PREFIX = "User Mgmt Test"
_VALIDATION_SHORT_CODE_RE = re.compile(r"^UM[0-9A-F]{6,12}$", re.I)


def _psql(sql: str) -> str:
    proc = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            "mssp-postgres",
            "psql",
            "-U",
            "mssp_admin",
            "-d",
            "mssp_control",
            "-v",
            "ON_ERROR_STOP=1",
            "-tAc",
            sql,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "psql failed")
    return (proc.stdout or "").strip()


def _psql_exec(sql: str) -> None:
    proc = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            "mssp-postgres",
            "psql",
            "-U",
            "mssp_admin",
            "-d",
            "mssp_control",
            "-v",
            "ON_ERROR_STOP=1",
        ],
        input=sql,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "psql failed")


def _is_protected_short_code(short_code: str) -> bool:
    upper = (short_code or "").upper()
    return any(upper.startswith(p.replace("-", "")) or upper.startswith(p) for p in _PROTECTED_TENANT_SHORT_PREFIXES)


def _validation_tenant_ids(extra_ids: Optional[List[str]] = None) -> List[str]:
    rows = _psql(
        """
        SELECT id::text || '|' || short_code || '|' || name
        FROM tenants
        WHERE name ILIKE 'User Mgmt Test%'
           OR short_code ~ '^UM[0-9A-F]+$';
        """
    )
    ids: List[str] = []
    for line in rows.splitlines():
        line = line.strip()
        if not line or "|" not in line:
            continue
        tid, short_code, name = line.split("|", 2)
        if _is_protected_short_code(short_code):
            continue
        if not name.startswith(_VALIDATION_NAME_PREFIX) and not _VALIDATION_SHORT_CODE_RE.match(short_code):
            continue
        ids.append(tid)
    if extra_ids:
        for tid in extra_ids:
            if tid and tid not in ids:
                ids.append(tid)
    return ids


def delete_validation_tenants(tenant_ids: Optional[List[str]] = None) -> int:
    """Remove validation tenants and their portal users; never touches MSSP staff."""
    ids = _validation_tenant_ids(tenant_ids)
    if not ids:
        return 0
    id_list = ", ".join(f"'{tid}'::uuid" for tid in ids)
    _psql_exec(
        f"""
        BEGIN;
        DELETE FROM audit_logs WHERE tenant_id IN ({id_list});
        DELETE FROM platform_users
        WHERE tenant_id IN ({id_list})
          AND role IN ('customer_admin', 'customer_viewer');
        DELETE FROM tenants
        WHERE id IN ({id_list})
          AND name ILIKE 'User Mgmt Test%';
        COMMIT;
        """
    )
    return len(ids)


def http(
    method: str,
    path: str,
    token: Optional[str] = None,
    body: Optional[Dict[str, Any]] = None,
    expect: Optional[int] = None,
) -> tuple[int, Dict[str, Any]]:
    url = f"{API}{path}"
    data = None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            status = resp.status
            raw = resp.read().decode("utf-8")
            payload = json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        status = e.code
        raw = e.read().decode("utf-8")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"detail": raw}
    if expect is not None and status != expect:
        raise AssertionError(f"{method} {path} expected {expect}, got {status}: {payload}")
    return status, payload


def login(email: str, password: str, portal: Optional[str] = None) -> str:
    body: Dict[str, Any] = {"email": email, "password": password}
    if portal:
        body["portal"] = portal
    _, data = http("POST", "/auth/login", body=body, expect=200)
    return data["access_token"]


def main() -> int:
    failures: list[str] = []
    suffix = os.urandom(4).hex()
    tenant_id: Optional[str] = None
    viewer_id: Optional[str] = None

    # Remove leftovers from interrupted prior runs.
    try:
        stale = delete_validation_tenants()
        if stale:
            print(f"INFO: cleaned {stale} stale validation tenant(s) before run")
    except Exception as e:
        print(f"WARN: could not clean stale validation tenants: {e}")

    try:
        admin_token = login(PLATFORM_EMAIL, PLATFORM_PASS, portal="admin")
    except Exception as e:
        print(f"FAIL: platform admin login — {e}")
        return 1

    tenant_code = f"UM{suffix}".upper()[:12]
    admin_email = f"um-admin-{suffix}@example.local"
    viewer_email = f"um-viewer-{suffix}@example.local"
    temp_pass = "TempPass123!"

    try:
        # 1) Onboard tenant + primary customer_admin via admin API
        try:
            _, tenant = http(
                "POST",
                "/v1/admin/customers",
                token=admin_token,
                body={
                    "name": f"User Mgmt Test {suffix}",
                    "short_code": tenant_code,
                    "status": "active",
                    "sla_level": "business",
                    "business_criticality": "medium",
                    "timezone": "Asia/Kolkata",
                    "deployment_mode": "cloud",
                    "cloud_provider": "aws",
                    "country": "IN",
                    "primary_contact_name": "UM Admin",
                    "primary_contact_email": admin_email,
                    "primary_contact_phone": "+10000000000",
                    "portal_admin": {
                        "email": admin_email,
                        "full_name": "UM Primary Admin",
                        "password": temp_pass,
                    },
                },
                expect=201,
            )
            tenant_id = tenant["id"]
            print(f"PASS: created tenant {tenant_code} ({tenant_id})")
        except Exception as e:
            print(f"FAIL: tenant onboard — {e}")
            return 1

        # 2) customer_admin creates viewer via v1 customer API
        try:
            cust_admin_token = login(admin_email, temp_pass, portal="customer")
            _, created = http(
                "POST",
                "/v1/customer/users",
                token=cust_admin_token,
                body={
                    "email": viewer_email,
                    "full_name": "UM Viewer",
                    "password": temp_pass,
                    "role": "customer_viewer",
                },
                expect=201,
            )
            viewer_id = created["id"]
            print("PASS: customer_admin created customer_viewer via /v1/customer/users")
        except Exception as e:
            failures.append(f"customer_admin create viewer: {e}")

        # 3) viewer forbidden on mutations
        try:
            if not viewer_id:
                raise RuntimeError("viewer not created")
            viewer_token = login(viewer_email, temp_pass, portal="customer")
            status, _ = http(
                "POST",
                "/v1/customer/users",
                token=viewer_token,
                body={
                    "email": f"blocked-{suffix}@example.local",
                    "full_name": "Blocked",
                    "password": temp_pass,
                    "role": "customer_viewer",
                },
            )
            if status != 403:
                failures.append(f"viewer create expected 403, got {status}")
            else:
                print("PASS: customer_viewer blocked from POST /v1/customer/users (403)")
            status, _ = http("DELETE", f"/v1/customer/users/{viewer_id}", token=viewer_token)
            if status != 403:
                failures.append(f"viewer delete expected 403, got {status}")
            else:
                print("PASS: customer_viewer blocked from DELETE (403)")
        except Exception as e:
            failures.append(f"viewer forbidden checks: {e}")

        # 4) MSSP admin governance on tenant users
        try:
            if not tenant_id or not viewer_id:
                raise RuntimeError("tenant or viewer missing")
            _, listing = http(
                "GET",
                f"/v1/admin/customers/{tenant_id}/users",
                token=admin_token,
                expect=200,
            )
            if len(listing.get("users") or []) < 2:
                failures.append("MSSP list users expected at least 2 portal users")
            else:
                print("PASS: MSSP lists tenant portal users")
            http(
                "PUT",
                f"/v1/admin/customers/{tenant_id}/users/{viewer_id}",
                token=admin_token,
                body={"status": "inactive"},
                expect=200,
            )
            print("PASS: MSSP disabled customer user via PUT")
        except Exception as e:
            failures.append(f"MSSP governance: {e}")

        # 5) Audit entries for mutations
        try:
            _, audits = http(
                "GET",
                f"/v1/admin/audit-logs?tenant_short_code={tenant_code}&limit=50",
                token=admin_token,
                expect=200,
            )
            events = audits.get("audit_logs") or audits.get("events") or audits.get("logs") or []
            actions = {e.get("action") for e in events}
            needed = {"USER_CREATED", "USER_DISABLED", "PASSWORD_RESET_FORCED"}
            if not needed.intersection(actions):
                if "USER_CREATED" not in actions:
                    failures.append(f"audit missing USER_CREATED; saw {sorted(actions)[:10]}")
                else:
                    print(f"PASS: audit contains USER_CREATED (actions sample: {sorted(actions)[:8]})")
            else:
                print(f"PASS: audit actions present: {sorted(needed.intersection(actions))}")
            if events:
                sample = events[0]
                if not sample.get("actor_email") and not sample.get("actor_role"):
                    failures.append("audit row missing actor_email/actor_role enrichment")
                else:
                    print("PASS: audit actor context present")
        except Exception as e:
            failures.append(f"audit verification: {e}")

        # 6) Customer user cannot authenticate to admin portal
        try:
            status, _ = http(
                "POST",
                "/auth/login",
                body={"email": admin_email, "password": temp_pass, "portal": "admin"},
            )
            if status != 403:
                failures.append(f"customer on admin portal login expected 403, got {status}")
            else:
                print("PASS: customer_admin blocked from admin portal login (403)")
        except Exception as e:
            failures.append(f"admin portal login guard: {e}")

        if failures:
            print("----")
            for f in failures:
                print(f"FAIL: {f}")
            return 1
        print("----")
        print("validate_user_management.py: ALL CHECKS PASSED")
        return 0
    finally:
        try:
            removed = delete_validation_tenants([tenant_id] if tenant_id else None)
            if removed:
                print(f"INFO: removed {removed} validation tenant(s) after run")
        except Exception as e:
            print(f"WARN: validation tenant cleanup failed: {e}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--cleanup-only":
        try:
            n = delete_validation_tenants()
            print(f"Removed {n} validation tenant(s).")
            sys.exit(0)
        except Exception as exc:
            print(f"Cleanup failed: {exc}")
            sys.exit(1)
    sys.exit(main())

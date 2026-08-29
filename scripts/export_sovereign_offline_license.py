#!/usr/bin/env python3
"""Export offline Sovereign Edge license JWS for field delivery (MSSP license factory)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = Path("/app") if Path("/app/app").is_dir() else ROOT / "backend-api"
sys.path.insert(0, str(APP_ROOT))

from app.db.session import fetch_one  # noqa: E402
from app.services.niktiar_license import LicenseSigningError, mint_license  # noqa: E402
from app.services.tenant_entitlement_defaults import current_tenant_service_ids  # noqa: E402


def resolve_tenant(*, tenant_short_code: str | None, tenant_id: str | None) -> dict:
    if tenant_id:
        row = fetch_one(
            """
            SELECT id::text, short_code, deployment_mode::text AS deployment_mode
            FROM tenants WHERE id = %s::uuid;
            """,
            (tenant_id,),
        )
    else:
        row = fetch_one(
            """
            SELECT id::text, short_code, deployment_mode::text AS deployment_mode
            FROM tenants WHERE short_code = %s;
            """,
            ((tenant_short_code or "").strip().upper(),),
        )
    if not row:
        raise SystemExit("tenant not found")
    return row


def resolve_appliance(tenant_id: str, appliance_id: str | None) -> dict:
    if appliance_id:
        row = fetch_one(
            """
            SELECT id::text, appliance_name, status
            FROM appliances
            WHERE id = %s::uuid AND tenant_id = %s::uuid;
            """,
            (appliance_id, tenant_id),
        )
    else:
        row = fetch_one(
            """
            SELECT id::text, appliance_name, status
            FROM appliances
            WHERE tenant_id = %s::uuid
            ORDER BY
              CASE status WHEN 'online' THEN 0 WHEN 'registered' THEN 1 ELSE 2 END,
              last_seen_at DESC NULLS LAST
            LIMIT 1;
            """,
            (tenant_id,),
        )
    if not row:
        raise SystemExit("no appliance registered for tenant")
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description="Export offline Sovereign Edge license JWS")
    parser.add_argument("--tenant-short-code", default="")
    parser.add_argument("--tenant-id", default="")
    parser.add_argument("--appliance-id", default="")
    parser.add_argument("--output", "-o", required=True, help="Output .jws path")
    parser.add_argument("--ttl-days", type=int, default=365)
    args = parser.parse_args()

    tenant = resolve_tenant(
        tenant_short_code=args.tenant_short_code or None,
        tenant_id=args.tenant_id or None,
    )
    appliance = resolve_appliance(tenant["id"], args.appliance_id or None)
    service_ids = current_tenant_service_ids(tenant["id"])
    if not service_ids:
        raise SystemExit("tenant has no entitled service_ids")

    try:
        minted = mint_license(
            tenant_id=tenant["id"],
            service_ids=service_ids,
            appliance_id=appliance["id"],
            core="svc-01" in {str(s).lower() for s in service_ids},
            ttl_seconds=max(1, args.ttl_days) * 24 * 3600,
        )
    except LicenseSigningError as exc:
        raise SystemExit(str(exc)) from exc

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(minted["license_jws"].strip() + "\n", encoding="utf-8")

    meta = {
        "tenant_short_code": tenant["short_code"],
        "tenant_id": tenant["id"],
        "deployment_mode": tenant.get("deployment_mode"),
        "appliance_id": appliance["id"],
        "appliance_name": appliance.get("appliance_name"),
        "service_ids": service_ids,
        "jti": minted["claims"].get("jti"),
        "exp": minted["claims"].get("exp"),
        "output": str(out),
    }
    print(json.dumps(meta, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

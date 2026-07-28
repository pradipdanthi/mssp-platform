"""KB-071: Tenant service entitlements + audit event write APIs."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator, model_validator

from app.api.dependencies import require_roles
from app.api.routes.admin import ADMIN_SOC_ROLES
from app.db.session import db_transaction, fetch_all, fetch_one, fetch_one_write
from app.services.audit_service import write_audit_event
from app.services.customer_safe_labels import entitlements_row_to_customer_public

router = APIRouter(tags=["kb071-entitlements-audit"])

PLATFORM_ADMIN = ("platform_admin",)
CUSTOMER_ROLES = ("customer_admin", "customer_viewer")

ALLOWED_SCAN_SCOPE = {
    "external_perimeter",
    "internal_network",
    "authenticated_hosts",
    "cloud_workloads",
    "web_applications",
}
ALLOWED_ENVIRONMENTS = {
    "production",
    "non_production",
    "remote_workforce",
    "ot_ics",
}
ALLOWED_COMPLIANCE = {
    "iso27001",
    "soc2",
    "pci_dss",
    "hipaa",
    "gdpr",
    "other",
}


class EntitlementsOut(BaseModel):
    tenant_id: str
    wazuh_siem: bool = True
    wazuh_retention_days: int = 30
    thehive_mode: str = "full"
    greenbone_enabled: bool = False
    greenbone_cadence: str = "monthly"
    shuffle_mode: str = "standard"
    # Roadmap modules (UI shows service capability names, not engine brands)
    zeek_enabled: bool = False
    misp_enabled: bool = False
    velociraptor_enabled: bool = False
    roadmap_notes: Optional[str] = None
    updated_at: Optional[str] = None


class CustomerEntitlementsPublic(BaseModel):
    """Customer portal only — no third-party engine field names."""

    tenant_id: str
    log_monitoring_enabled: bool = True
    log_retention_days: int = 30
    incident_response: str = "included"
    vulnerability_management_enabled: bool = False
    vulnerability_scan_cadence: str = "monthly"
    security_automation: str = "included"
    network_traffic_analysis_enabled: bool = False
    threat_intelligence_enabled: bool = False
    endpoint_forensics_enabled: bool = False
    updated_at: Optional[str] = None


class EntitlementsUpdate(BaseModel):
    wazuh_siem: Optional[bool] = None
    wazuh_retention_days: Optional[int] = Field(default=None, ge=30, le=365)
    thehive_mode: Optional[str] = None
    greenbone_enabled: Optional[bool] = None
    greenbone_cadence: Optional[str] = None
    shuffle_mode: Optional[str] = None
    zeek_enabled: Optional[bool] = None
    misp_enabled: Optional[bool] = None
    velociraptor_enabled: Optional[bool] = None
    roadmap_notes: Optional[str] = None


class AuditEventCreate(BaseModel):
    action: str = Field(min_length=2, max_length=120)
    entity_type: str = Field(min_length=2, max_length=80)
    entity_id: Optional[str] = None
    tenant_id: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)


DEFAULTS = {
    "wazuh_siem": True,
    "wazuh_retention_days": 30,
    "thehive_mode": "full",
    "greenbone_enabled": False,
    "greenbone_cadence": "monthly",
    "shuffle_mode": "standard",
    "zeek_enabled": False,
    "misp_enabled": False,
    "velociraptor_enabled": False,
    "roadmap_notes": None,
}


def upsert_tenant_entitlements(
    tenant_id: str,
    values: Dict[str, Any],
    *,
    actor_user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Insert/update entitlements row. Used by PUT API and tenant create (KB-075)."""
    merged = {**DEFAULTS, **{k: v for k, v in values.items() if k in DEFAULTS}}
    if merged["wazuh_retention_days"] not in (30, 90, 365):
        raise ValueError("Invalid wazuh_retention_days")
    if merged["thehive_mode"] not in ("full", "read_only", "off"):
        raise ValueError("Invalid thehive_mode")
    if merged["greenbone_cadence"] not in ("weekly", "monthly", "off"):
        raise ValueError("Invalid greenbone_cadence")
    if merged["shuffle_mode"] not in ("standard", "custom", "off"):
        raise ValueError("Invalid shuffle_mode")
    notes = merged.get("roadmap_notes")
    if notes is not None and len(str(notes)) > 2000:
        raise ValueError("roadmap_notes too long")

    row = fetch_one_write(
        """
        INSERT INTO tenant_entitlements (
            tenant_id, wazuh_siem, wazuh_retention_days, thehive_mode,
            greenbone_enabled, greenbone_cadence, shuffle_mode,
            zeek_enabled, misp_enabled, velociraptor_enabled, roadmap_notes,
            updated_by
        ) VALUES (
            %s::uuid, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::uuid
        )
        ON CONFLICT (tenant_id) DO UPDATE SET
            wazuh_siem = EXCLUDED.wazuh_siem,
            wazuh_retention_days = EXCLUDED.wazuh_retention_days,
            thehive_mode = EXCLUDED.thehive_mode,
            greenbone_enabled = EXCLUDED.greenbone_enabled,
            greenbone_cadence = EXCLUDED.greenbone_cadence,
            shuffle_mode = EXCLUDED.shuffle_mode,
            zeek_enabled = EXCLUDED.zeek_enabled,
            misp_enabled = EXCLUDED.misp_enabled,
            velociraptor_enabled = EXCLUDED.velociraptor_enabled,
            roadmap_notes = EXCLUDED.roadmap_notes,
            updated_by = EXCLUDED.updated_by,
            updated_at = now()
        RETURNING
            tenant_id::text,
            wazuh_siem,
            wazuh_retention_days,
            thehive_mode,
            greenbone_enabled,
            greenbone_cadence,
            shuffle_mode,
            COALESCE(zeek_enabled, FALSE) AS zeek_enabled,
            COALESCE(misp_enabled, FALSE) AS misp_enabled,
            COALESCE(velociraptor_enabled, FALSE) AS velociraptor_enabled,
            roadmap_notes,
            updated_at::text;
        """,
        (
            tenant_id,
            merged["wazuh_siem"],
            merged["wazuh_retention_days"],
            merged["thehive_mode"],
            merged["greenbone_enabled"],
            merged["greenbone_cadence"],
            merged["shuffle_mode"],
            merged["zeek_enabled"],
            merged["misp_enabled"],
            merged["velociraptor_enabled"],
            merged.get("roadmap_notes"),
            actor_user_id,
        ),
    )
    return row or {"tenant_id": tenant_id, **merged}


def _fetch_entitlements(tenant_id: UUID) -> Optional[Dict[str, Any]]:
    return fetch_one(
        """
        SELECT
            tenant_id::text,
            wazuh_siem,
            wazuh_retention_days,
            thehive_mode,
            greenbone_enabled,
            greenbone_cadence,
            shuffle_mode,
            COALESCE(zeek_enabled, FALSE) AS zeek_enabled,
            COALESCE(misp_enabled, FALSE) AS misp_enabled,
            COALESCE(velociraptor_enabled, FALSE) AS velociraptor_enabled,
            roadmap_notes,
            updated_at::text
        FROM tenant_entitlements
        WHERE tenant_id = %s;
        """,
        (str(tenant_id),),
    )


def _ensure_tenant(tenant_id: UUID) -> None:
    row = fetch_one("SELECT id::text FROM tenants WHERE id = %s;", (str(tenant_id),))
    if not row:
        raise HTTPException(status_code=404, detail="Tenant not found")


@router.get("/admin/tenants/{tenant_id}/entitlements", response_model=EntitlementsOut)
def get_tenant_entitlements(
    tenant_id: UUID,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> EntitlementsOut:
    _ensure_tenant(tenant_id)
    row = _fetch_entitlements(tenant_id)
    if not row:
        return EntitlementsOut(tenant_id=str(tenant_id), **DEFAULTS)
    return EntitlementsOut(**row)


@router.put("/admin/tenants/{tenant_id}/entitlements", response_model=EntitlementsOut)
def put_tenant_entitlements(
    tenant_id: UUID,
    payload: EntitlementsUpdate,
    request: Request,
    current_user: Dict[str, Any] = Depends(require_roles(*PLATFORM_ADMIN)),
) -> EntitlementsOut:
    _ensure_tenant(tenant_id)
    existing = _fetch_entitlements(tenant_id) or {"tenant_id": str(tenant_id), **DEFAULTS}
    merged = {**DEFAULTS, **{k: v for k, v in existing.items() if k in DEFAULTS}}
    for key, value in payload.model_dump(exclude_unset=True).items():
        if key == "roadmap_notes":
            merged[key] = value
        elif value is not None:
            merged[key] = value

    try:
        row = upsert_tenant_entitlements(
            str(tenant_id),
            merged,
            actor_user_id=current_user.get("id"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    write_audit_event(
        action="tenant.entitlements_updated",
        entity_type="tenant",
        entity_id=str(tenant_id),
        tenant_id=str(tenant_id),
        actor_user_id=current_user.get("id"),
        source_ip=request.client.host if request.client else None,
        details={"before": existing, "after": row},
    )
    return EntitlementsOut(**(row or merged))


@router.get("/customer/entitlements/{short_code}", response_model=CustomerEntitlementsPublic)
def get_customer_entitlements(
    short_code: str,
    current_user: Dict[str, Any] = Depends(
        require_roles("customer_admin", "customer_viewer", *ADMIN_SOC_ROLES)
    ),
) -> CustomerEntitlementsPublic:
    tenant = fetch_one(
        "SELECT id::text FROM tenants WHERE upper(short_code) = upper(%s);",
        (short_code,),
    )
    if not tenant:
        raise HTTPException(status_code=404, detail="Not found")
    if current_user.get("role") in ("customer_admin", "customer_viewer"):
        user_tenant = current_user.get("tenant_id")
        if not user_tenant or str(user_tenant) != tenant["id"]:
            raise HTTPException(status_code=404, detail="Not found")
    row = _fetch_entitlements(UUID(tenant["id"]))
    base = {**DEFAULTS, "tenant_id": tenant["id"]}
    if row:
        base.update({k: row[k] for k in DEFAULTS if k in row})
        base["tenant_id"] = tenant["id"]
        if row.get("updated_at") is not None:
            base["updated_at"] = row["updated_at"]
    return CustomerEntitlementsPublic(**entitlements_row_to_customer_public(base))


@router.post("/admin/audit-events")
def create_audit_event(
    payload: AuditEventCreate,
    request: Request,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    row = write_audit_event(
        action=payload.action,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        tenant_id=payload.tenant_id,
        actor_user_id=current_user.get("id"),
        source_ip=request.client.host if request.client else None,
        details=payload.details,
    )
    return {"audit_event": row}


# --- KB-076: service upgrade / interest requests ---


class ServiceUpgradeCreate(BaseModel):
    service_key: Literal[
        "vulnerability_management",
        "network_traffic_analysis",
        "threat_intelligence",
        "endpoint_forensics",
        "other",
    ] = "vulnerability_management"
    preferred_cadence: Literal["weekly", "monthly", "quarterly", "unsure"] = "monthly"
    scan_scope: List[str] = Field(default_factory=list)
    approximate_assets: Optional[int] = Field(default=None, ge=1, le=1000000)
    environments: List[str] = Field(default_factory=list)
    urgency: Literal["exploring", "planning", "needed_soon", "urgent"] = "exploring"
    compliance_drivers: List[str] = Field(default_factory=list)
    requirements_summary: str = Field(min_length=10, max_length=4000)
    preferred_contact: Literal["email", "phone", "either"] = "email"
    contact_phone: Optional[str] = Field(default=None, max_length=40)

    @field_validator("requirements_summary")
    @classmethod
    def strip_summary(cls, value: str) -> str:
        return value.strip()

    @field_validator("contact_phone", mode="before")
    @classmethod
    def blank_phone(cls, value: object) -> object:
        if value is None or value == "":
            return None
        return value

    @model_validator(mode="after")
    def validate_lists(self) -> "ServiceUpgradeCreate":
        bad_scope = [x for x in self.scan_scope if x not in ALLOWED_SCAN_SCOPE]
        if bad_scope:
            raise ValueError(f"Invalid scan_scope values: {bad_scope}")
        bad_env = [x for x in self.environments if x not in ALLOWED_ENVIRONMENTS]
        if bad_env:
            raise ValueError(f"Invalid environments values: {bad_env}")
        bad_comp = [x for x in self.compliance_drivers if x not in ALLOWED_COMPLIANCE]
        if bad_comp:
            raise ValueError(f"Invalid compliance_drivers values: {bad_comp}")
        if self.preferred_contact == "phone" and not self.contact_phone:
            raise ValueError("contact_phone is required when preferred_contact is phone")
        return self


class ServiceUpgradeOut(BaseModel):
    id: str
    tenant_id: str
    tenant_name: Optional[str] = None
    short_code: Optional[str] = None
    requested_by_user_id: Optional[str] = None
    requested_by_name: Optional[str] = None
    service_key: str
    preferred_cadence: str
    scan_scope: List[str]
    approximate_assets: Optional[int] = None
    environments: List[str]
    urgency: str
    compliance_drivers: List[str]
    requirements_summary: str
    preferred_contact: str
    contact_phone: Optional[str] = None
    status: str
    admin_notes: Optional[str] = None
    created_at: str
    updated_at: Optional[str] = None


def _resolve_customer_tenant(short_code: str, current_user: Dict[str, Any]) -> Dict[str, Any]:
    tenant = fetch_one(
        "SELECT id::text, name, short_code FROM tenants WHERE upper(short_code) = upper(%s);",
        (short_code,),
    )
    if not tenant:
        raise HTTPException(status_code=404, detail="Not found")
    if current_user.get("role") in CUSTOMER_ROLES:
        user_tenant = current_user.get("tenant_id")
        if not user_tenant or str(user_tenant) != tenant["id"]:
            raise HTTPException(status_code=404, detail="Not found")
    return tenant


def _row_to_upgrade(row: Dict[str, Any]) -> ServiceUpgradeOut:
    return ServiceUpgradeOut(
        id=row["id"],
        tenant_id=row["tenant_id"],
        tenant_name=row.get("tenant_name"),
        short_code=row.get("short_code"),
        requested_by_user_id=row.get("requested_by_user_id"),
        requested_by_name=row.get("requested_by_name"),
        service_key=row["service_key"],
        preferred_cadence=row["preferred_cadence"],
        scan_scope=list(row.get("scan_scope") or []),
        approximate_assets=row.get("approximate_assets"),
        environments=list(row.get("environments") or []),
        urgency=row["urgency"],
        compliance_drivers=list(row.get("compliance_drivers") or []),
        requirements_summary=row["requirements_summary"],
        preferred_contact=row["preferred_contact"],
        contact_phone=row.get("contact_phone"),
        status=row["status"],
        admin_notes=row.get("admin_notes"),
        created_at=row["created_at"],
        updated_at=row.get("updated_at"),
    )


@router.post(
    "/customer/service-upgrade-requests/{short_code}",
    response_model=ServiceUpgradeOut,
    status_code=201,
)
def create_customer_service_upgrade_request(
    short_code: str,
    payload: ServiceUpgradeCreate,
    request: Request,
    current_user: Dict[str, Any] = Depends(require_roles(*CUSTOMER_ROLES, *ADMIN_SOC_ROLES)),
) -> ServiceUpgradeOut:
    """Customer submits interest / upgrade details for an optional service."""
    tenant = _resolve_customer_tenant(short_code, current_user)

    open_existing = fetch_one(
        """
        SELECT id::text FROM service_upgrade_requests
        WHERE tenant_id = %s::uuid
          AND service_key = %s
          AND status IN ('submitted', 'reviewing', 'quoted')
        LIMIT 1;
        """,
        (tenant["id"], payload.service_key),
    )
    if open_existing:
        raise HTTPException(
            status_code=409,
            detail="An open upgrade request for this service already exists. Your MSSP will follow up.",
        )

    row = fetch_one_write(
        """
        INSERT INTO service_upgrade_requests (
            tenant_id, requested_by_user_id, service_key, preferred_cadence,
            scan_scope, approximate_assets, environments, urgency,
            compliance_drivers, requirements_summary, preferred_contact, contact_phone
        ) VALUES (
            %s::uuid, %s::uuid, %s, %s,
            %s::text[], %s, %s::text[], %s,
            %s::text[], %s, %s, %s
        )
        RETURNING
            id::text,
            tenant_id::text,
            requested_by_user_id::text,
            service_key,
            preferred_cadence,
            scan_scope,
            approximate_assets,
            environments,
            urgency,
            compliance_drivers,
            requirements_summary,
            preferred_contact,
            contact_phone,
            status,
            created_at::text,
            updated_at::text;
        """,
        (
            tenant["id"],
            current_user.get("id"),
            payload.service_key,
            payload.preferred_cadence,
            payload.scan_scope,
            payload.approximate_assets,
            payload.environments,
            payload.urgency,
            payload.compliance_drivers,
            payload.requirements_summary,
            payload.preferred_contact,
            payload.contact_phone,
        ),
    )
    if not row:
        raise HTTPException(status_code=500, detail="Could not save upgrade request")

    write_audit_event(
        action="service_upgrade.requested",
        entity_type="service_upgrade_request",
        entity_id=row["id"],
        tenant_id=tenant["id"],
        actor_user_id=current_user.get("id"),
        source_ip=request.client.host if request.client else None,
        details={
            "service_key": payload.service_key,
            "urgency": payload.urgency,
            "preferred_cadence": payload.preferred_cadence,
        },
    )

    row["tenant_name"] = tenant["name"]
    row["short_code"] = tenant["short_code"]
    row["requested_by_name"] = current_user.get("full_name")
    return _row_to_upgrade(row)


@router.get(
    "/customer/service-upgrade-requests/{short_code}",
    response_model=Dict[str, Any],
)
def list_customer_service_upgrade_requests(
    short_code: str,
    current_user: Dict[str, Any] = Depends(require_roles(*CUSTOMER_ROLES, *ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    tenant = _resolve_customer_tenant(short_code, current_user)
    rows = fetch_all(
        """
        SELECT
            r.id::text,
            r.tenant_id::text,
            t.name AS tenant_name,
            t.short_code,
            r.requested_by_user_id::text,
            u.full_name AS requested_by_name,
            r.service_key,
            r.preferred_cadence,
            r.scan_scope,
            r.approximate_assets,
            r.environments,
            r.urgency,
            r.compliance_drivers,
            r.requirements_summary,
            r.preferred_contact,
            r.contact_phone,
            r.status,
            r.admin_notes,
            r.created_at::text,
            r.updated_at::text
        FROM service_upgrade_requests r
        JOIN tenants t ON t.id = r.tenant_id
        LEFT JOIN platform_users u ON u.id = r.requested_by_user_id
        WHERE r.tenant_id = %s::uuid
        ORDER BY r.created_at DESC
        LIMIT 50;
        """,
        (tenant["id"],),
    )
    return {"requests": [_row_to_upgrade(r).model_dump() for r in rows]}


@router.get("/admin/service-upgrade-requests", response_model=Dict[str, Any])
def list_admin_service_upgrade_requests(
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    rows = fetch_all(
        """
        SELECT
            r.id::text,
            r.tenant_id::text,
            t.name AS tenant_name,
            t.short_code,
            r.requested_by_user_id::text,
            u.full_name AS requested_by_name,
            r.service_key,
            r.preferred_cadence,
            r.scan_scope,
            r.approximate_assets,
            r.environments,
            r.urgency,
            r.compliance_drivers,
            r.requirements_summary,
            r.preferred_contact,
            r.contact_phone,
            r.status,
            r.admin_notes,
            r.created_at::text,
            r.updated_at::text
        FROM service_upgrade_requests r
        JOIN tenants t ON t.id = r.tenant_id
        LEFT JOIN platform_users u ON u.id = r.requested_by_user_id
        ORDER BY
            CASE r.status
                WHEN 'submitted' THEN 1
                WHEN 'reviewing' THEN 2
                WHEN 'quoted' THEN 3
                ELSE 4
            END,
            r.created_at DESC
        LIMIT 200;
        """,
    )
    return {"requests": [_row_to_upgrade(r).model_dump() for r in rows]}


def _fetch_upgrade_request(request_id: str) -> Optional[Dict[str, Any]]:
    return fetch_one(
        """
        SELECT
            r.id::text,
            r.tenant_id::text,
            t.name AS tenant_name,
            t.short_code,
            r.requested_by_user_id::text,
            u.full_name AS requested_by_name,
            r.service_key,
            r.preferred_cadence,
            r.scan_scope,
            r.approximate_assets,
            r.environments,
            r.urgency,
            r.compliance_drivers,
            r.requirements_summary,
            r.preferred_contact,
            r.contact_phone,
            r.status,
            r.admin_notes,
            r.created_at::text,
            r.updated_at::text
        FROM service_upgrade_requests r
        JOIN tenants t ON t.id = r.tenant_id
        LEFT JOIN platform_users u ON u.id = r.requested_by_user_id
        WHERE r.id = %s::uuid;
        """,
        (request_id,),
    )


def _vuln_cadence_from_request(preferred: str) -> str:
    p = (preferred or "").strip().lower()
    if p == "weekly":
        return "weekly"
    return "monthly"


class ServiceUpgradePatch(BaseModel):
    status: Optional[
        Literal["submitted", "reviewing", "quoted", "accepted", "declined", "closed"]
    ] = None
    admin_notes: Optional[str] = Field(default=None, max_length=4000)


@router.patch(
    "/admin/service-upgrade-requests/{request_id}",
    response_model=ServiceUpgradeOut,
)
def patch_admin_service_upgrade_request(
    request_id: UUID,
    payload: ServiceUpgradePatch,
    request: Request,
    current_user: Dict[str, Any] = Depends(require_roles("platform_admin", "soc_manager")),
) -> ServiceUpgradeOut:
    """Update request status (e.g. mark as reviewing)."""
    if payload.status is None and payload.admin_notes is None:
        raise HTTPException(status_code=422, detail="No changes provided")
    existing = _fetch_upgrade_request(str(request_id))
    if not existing:
        raise HTTPException(status_code=404, detail="Upgrade request not found")
    row = fetch_one_write(
        """
        UPDATE service_upgrade_requests
        SET
            status = COALESCE(%s, status),
            admin_notes = COALESCE(%s, admin_notes),
            updated_at = now()
        WHERE id = %s::uuid
        RETURNING
            id::text,
            tenant_id::text,
            requested_by_user_id::text,
            service_key,
            preferred_cadence,
            scan_scope,
            approximate_assets,
            environments,
            urgency,
            compliance_drivers,
            requirements_summary,
            preferred_contact,
            contact_phone,
            status,
            admin_notes,
            created_at::text,
            updated_at::text;
        """,
        (payload.status, payload.admin_notes, str(request_id)),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Upgrade request not found")
    row["tenant_name"] = existing.get("tenant_name")
    row["short_code"] = existing.get("short_code")
    row["requested_by_name"] = existing.get("requested_by_name")
    write_audit_event(
        action="service_upgrade.updated",
        entity_type="service_upgrade_request",
        entity_id=str(request_id),
        tenant_id=existing["tenant_id"],
        actor_user_id=current_user.get("id"),
        source_ip=request.client.host if request.client else None,
        details={"status": payload.status},
    )
    return _row_to_upgrade(row)


@router.post(
    "/admin/service-upgrade-requests/{request_id}/approve-enable",
    response_model=Dict[str, Any],
)
def approve_and_enable_service_upgrade(
    request_id: UUID,
    request: Request,
    current_user: Dict[str, Any] = Depends(require_roles("platform_admin", "soc_manager")),
) -> Dict[str, Any]:
    """
    MSSP workflow: accept customer request, turn on the matching entitlement,
    queue automated vulnerability scan (when applicable).
    """
    existing = _fetch_upgrade_request(str(request_id))
    if not existing:
        raise HTTPException(status_code=404, detail="Upgrade request not found")
    if existing["status"] in ("accepted", "declined", "closed"):
        raise HTTPException(
            status_code=409,
            detail=f"Request already {existing['status']}.",
        )

    tenant_id = existing["tenant_id"]
    service_key = existing["service_key"]
    next_steps: List[str] = []

    if service_key == "vulnerability_management":
        current_ent = _fetch_entitlements(UUID(tenant_id)) or dict(DEFAULTS)
        cadence = _vuln_cadence_from_request(existing["preferred_cadence"])
        merged = {
            **DEFAULTS,
            **{k: current_ent.get(k) for k in DEFAULTS if k in current_ent},
            "greenbone_enabled": True,
            "greenbone_cadence": cadence,
        }
        upsert_tenant_entitlements(
            tenant_id,
            merged,
            actor_user_id=current_user.get("id"),
        )
        with db_transaction() as cur:
            cur.execute(
                """
                UPDATE tenant_entitlements
                SET last_vuln_scan_at = NULL, updated_at = now()
                WHERE tenant_id = %s::uuid;
                """,
                (tenant_id,),
            )
        asset_count = fetch_one(
            """
            SELECT count(*)::int AS n
            FROM protected_assets
            WHERE tenant_id = %s::uuid AND status = 'active'
              AND (ip_address IS NOT NULL OR coalesce(hostname, '') <> '');
            """,
            (tenant_id,),
        )
        n_assets = int(asset_count["n"]) if asset_count else 0
        if n_assets == 0:
            next_steps.append(
                "Add protected assets (IP or hostname) in Admin → Assets for this customer "
                "so automated scans have targets."
            )
        else:
            next_steps.append(
                f"Automated scanning will run on the next cycle (~15 minutes) for {n_assets} "
                "protected asset(s)."
            )
        next_steps.append(
            "After findings appear under Vulnerabilities, promote high/critical items to "
            "customer-visible recommendations."
        )
    else:
        next_steps.append(
            "This service type is not auto-provisioned yet. Enable entitlements manually "
            "under the customer subscription panel."
        )

    row = fetch_one_write(
        """
        UPDATE service_upgrade_requests
        SET status = 'accepted', updated_at = now()
        WHERE id = %s::uuid
        RETURNING id::text;
        """,
        (str(request_id),),
    )
    if not row:
        raise HTTPException(status_code=500, detail="Could not update request")

    write_audit_event(
        action="service_upgrade.approved",
        entity_type="service_upgrade_request",
        entity_id=str(request_id),
        tenant_id=tenant_id,
        actor_user_id=current_user.get("id"),
        source_ip=request.client.host if request.client else None,
        details={"service_key": service_key},
    )

    return {
        "request": _row_to_upgrade({**existing, "status": "accepted"}).model_dump(),
        "entitlements_updated": service_key == "vulnerability_management",
        "message": (
            "Vulnerability Management is now enabled for this customer. "
            "They will see the active service on their next portal refresh."
            if service_key == "vulnerability_management"
            else "Request marked accepted."
        ),
        "next_steps": next_steps,
    }


@router.post(
    "/admin/service-upgrade-requests/{request_id}/decline",
    response_model=ServiceUpgradeOut,
)
def decline_service_upgrade(
    request_id: UUID,
    request: Request,
    current_user: Dict[str, Any] = Depends(require_roles("platform_admin", "soc_manager")),
) -> ServiceUpgradeOut:
    existing = _fetch_upgrade_request(str(request_id))
    if not existing:
        raise HTTPException(status_code=404, detail="Upgrade request not found")
    row = fetch_one_write(
        """
        UPDATE service_upgrade_requests
        SET status = 'declined', updated_at = now()
        WHERE id = %s::uuid
        RETURNING
            id::text,
            tenant_id::text,
            requested_by_user_id::text,
            service_key,
            preferred_cadence,
            scan_scope,
            approximate_assets,
            environments,
            urgency,
            compliance_drivers,
            requirements_summary,
            preferred_contact,
            contact_phone,
            status,
            admin_notes,
            created_at::text,
            updated_at::text;
        """,
        (str(request_id),),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Upgrade request not found")
    row["tenant_name"] = existing.get("tenant_name")
    row["short_code"] = existing.get("short_code")
    row["requested_by_name"] = existing.get("requested_by_name")
    write_audit_event(
        action="service_upgrade.declined",
        entity_type="service_upgrade_request",
        entity_id=str(request_id),
        tenant_id=existing["tenant_id"],
        actor_user_id=current_user.get("id"),
        source_ip=request.client.host if request.client else None,
        details={},
    )
    return _row_to_upgrade(row)

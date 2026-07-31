"""KB-071: Tenant service entitlements + audit event write APIs."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator, model_validator

from app.api.dependencies import require_roles
from app.api.routes.admin import ADMIN_SOC_ROLES
from app.db.session import db_transaction, fetch_all, fetch_one, fetch_one_write
from app.services.asset_service_coverage import (
    coverage_picker_payload,
    replace_coverage,
    summarize_assets,
    validate_tenant_asset_ids,
)
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
    continuous_compliance_enabled: bool = False
    external_attack_surface_enabled: bool = False
    cloud_identity_protection_enabled: bool = False
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
    continuous_compliance_enabled: bool = False
    external_attack_surface_enabled: bool = False
    cloud_identity_protection_enabled: bool = False
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
    continuous_compliance_enabled: Optional[bool] = None
    external_attack_surface_enabled: Optional[bool] = None
    cloud_identity_protection_enabled: Optional[bool] = None
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
    "continuous_compliance_enabled": False,
    "external_attack_surface_enabled": False,
    "cloud_identity_protection_enabled": False,
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
            zeek_enabled, misp_enabled, velociraptor_enabled,
            continuous_compliance_enabled, external_attack_surface_enabled,
            cloud_identity_protection_enabled,
            roadmap_notes,
            updated_by
        ) VALUES (
            %s::uuid, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::uuid
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
            continuous_compliance_enabled = EXCLUDED.continuous_compliance_enabled,
            external_attack_surface_enabled = EXCLUDED.external_attack_surface_enabled,
            cloud_identity_protection_enabled = EXCLUDED.cloud_identity_protection_enabled,
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
            COALESCE(continuous_compliance_enabled, FALSE) AS continuous_compliance_enabled,
            COALESCE(external_attack_surface_enabled, FALSE) AS external_attack_surface_enabled,
            COALESCE(cloud_identity_protection_enabled, FALSE) AS cloud_identity_protection_enabled,
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
            merged["continuous_compliance_enabled"],
            merged["external_attack_surface_enabled"],
            merged["cloud_identity_protection_enabled"],
            merged.get("roadmap_notes"),
            actor_user_id,
        ),
    )
    return row or {"tenant_id": tenant_id, **merged}


def _fetch_entitlements(tenant_id: UUID) -> Optional[Dict[str, Any]]:
    return fetch_one(
        """
        SELECT
            e.tenant_id::text,
            e.wazuh_siem,
            e.wazuh_retention_days,
            e.thehive_mode,
            e.greenbone_enabled,
            e.greenbone_cadence,
            e.shuffle_mode,
            COALESCE(e.zeek_enabled, FALSE) AS zeek_enabled,
            COALESCE(e.misp_enabled, FALSE) AS misp_enabled,
            COALESCE(e.velociraptor_enabled, FALSE) AS velociraptor_enabled,
            COALESCE(e.continuous_compliance_enabled, FALSE) AS continuous_compliance_enabled,
            COALESCE(e.external_attack_surface_enabled, FALSE) AS external_attack_surface_enabled,
            COALESCE(e.cloud_identity_protection_enabled, FALSE) AS cloud_identity_protection_enabled,
            EXISTS (
                SELECT 1 FROM tenant_compliance_summaries s
                WHERE s.tenant_id = e.tenant_id AND s.total_checks > 0
            ) AS has_compliance_data,
            EXISTS (
                SELECT 1 FROM tenant_easm_assets ea
                WHERE ea.tenant_id = e.tenant_id AND ea.status = 'ACTIVE'
            ) AS has_easm_data,
            EXISTS (
                SELECT 1 FROM tenant_cloud_identity_configs ic
                WHERE ic.tenant_id = e.tenant_id AND ic.status = 'CONNECTED'
            ) AS has_itdr_data,
            e.roadmap_notes,
            e.updated_at::text
        FROM tenant_entitlements e
        WHERE e.tenant_id = %s;
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
        base["has_compliance_data"] = bool(row.get("has_compliance_data"))
        base["has_easm_data"] = bool(row.get("has_easm_data"))
        base["has_itdr_data"] = bool(row.get("has_itdr_data"))
        if row.get("updated_at") is not None:
            base["updated_at"] = row["updated_at"]
    else:
        has = fetch_one(
            """
            SELECT 1 AS ok FROM tenant_compliance_summaries
            WHERE tenant_id = %s::uuid AND total_checks > 0 LIMIT 1;
            """,
            (tenant["id"],),
        )
        has_easm = fetch_one(
            """
            SELECT 1 AS ok FROM tenant_easm_assets
            WHERE tenant_id = %s::uuid AND status = 'ACTIVE' LIMIT 1;
            """,
            (tenant["id"],),
        )
        has_itdr = fetch_one(
            """
            SELECT 1 AS ok FROM tenant_cloud_identity_configs
            WHERE tenant_id = %s::uuid AND status = 'CONNECTED' LIMIT 1;
            """,
            (tenant["id"],),
        )
        base["has_compliance_data"] = bool(has)
        base["has_easm_data"] = bool(has_easm)
        base["has_itdr_data"] = bool(has_itdr)
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
        "security_automation",
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
    requested_asset_ids: List[UUID] = Field(default_factory=list)

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
        if self.service_key == "vulnerability_management" and not self.requested_asset_ids:
            raise ValueError(
                "Select at least one protected asset for Vulnerability Management coverage."
            )
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
    requested_asset_ids: List[str] = Field(default_factory=list)
    requested_assets: List[Dict[str, Any]] = Field(default_factory=list)


class ServiceUpgradeApproveBody(BaseModel):
    """Optional asset selection when approving (defaults to customer's requested set)."""

    asset_ids: Optional[List[UUID]] = None


class AssetCoveragePut(BaseModel):
    service_key: Literal[
        "vulnerability_management",
        "network_traffic_analysis",
        "threat_intelligence",
        "endpoint_forensics",
        "security_automation",
        "other",
    ] = "vulnerability_management"
    asset_ids: List[UUID] = Field(default_factory=list)
    enable_entitlement: bool = True
    greenbone_cadence: Optional[Literal["weekly", "monthly", "off"]] = None


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
    raw_ids = row.get("requested_asset_ids") or []
    if isinstance(raw_ids, str):
        # unlikely; keep safe
        asset_ids = []
    else:
        asset_ids = [str(x) for x in raw_ids if x]
    requested_assets = row.get("requested_assets")
    if requested_assets is None and asset_ids and row.get("tenant_id"):
        requested_assets = summarize_assets(str(row["tenant_id"]), asset_ids)
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
        requested_asset_ids=asset_ids,
        requested_assets=list(requested_assets or []),
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

    requested_ids = validate_tenant_asset_ids(
        tenant["id"], [str(x) for x in payload.requested_asset_ids]
    )
    if payload.service_key == "vulnerability_management" and not requested_ids:
        raise HTTPException(
            status_code=422,
            detail="Select at least one of your protected assets for Vulnerability Management.",
        )
    approx = payload.approximate_assets
    if approx is None and requested_ids:
        approx = len(requested_ids)

    row = fetch_one_write(
        """
        INSERT INTO service_upgrade_requests (
            tenant_id, requested_by_user_id, service_key, preferred_cadence,
            scan_scope, approximate_assets, environments, urgency,
            compliance_drivers, requirements_summary, preferred_contact, contact_phone,
            requested_asset_ids
        ) VALUES (
            %s::uuid, %s::uuid, %s, %s,
            %s::text[], %s, %s::text[], %s,
            %s::text[], %s, %s, %s,
            %s::uuid[]
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
            updated_at::text,
            requested_asset_ids;
        """,
        (
            tenant["id"],
            current_user.get("id"),
            payload.service_key,
            payload.preferred_cadence,
            payload.scan_scope,
            approx,
            payload.environments,
            payload.urgency,
            payload.compliance_drivers,
            payload.requirements_summary,
            payload.preferred_contact,
            payload.contact_phone,
            requested_ids,
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
            "requested_asset_count": len(requested_ids),
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
            r.updated_at::text,
            r.requested_asset_ids
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
            r.updated_at::text,
            r.requested_asset_ids
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
            r.updated_at::text,
            r.requested_asset_ids
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
            updated_at::text,
            requested_asset_ids;
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
    payload: ServiceUpgradeApproveBody = ServiceUpgradeApproveBody(),
    current_user: Dict[str, Any] = Depends(require_roles("platform_admin", "soc_manager")),
) -> Dict[str, Any]:
    """
    MSSP workflow: accept customer request, turn on the matching entitlement,
    optionally scope Vulnerability Management to selected assets.
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
    entitlements_updated = False
    covered_count = 0

    chosen_ids: List[str] = []
    if payload.asset_ids is not None:
        chosen_ids = validate_tenant_asset_ids(tenant_id, [str(x) for x in payload.asset_ids])
    else:
        raw = existing.get("requested_asset_ids") or []
        chosen_ids = validate_tenant_asset_ids(tenant_id, [str(x) for x in raw])

    if service_key == "vulnerability_management":
        if not chosen_ids:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Select at least one protected asset to cover with Vulnerability Management "
                    "before approving."
                ),
            )
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
        cov = replace_coverage(
            tenant_id=tenant_id,
            service_key="vulnerability_management",
            asset_ids=chosen_ids,
            actor_user_id=current_user.get("id"),
        )
        covered_count = int(cov.get("covered_count") or 0)
        with db_transaction() as cur:
            cur.execute(
                """
                UPDATE tenant_entitlements
                SET last_vuln_scan_at = NULL, updated_at = now()
                WHERE tenant_id = %s::uuid;
                """,
                (tenant_id,),
            )
        next_steps.append(
            f"Vulnerability Management enabled for {covered_count} selected asset(s) only "
            "(not the full estate)."
        )
        next_steps.append(
            "Automated scanning will run on the next cycle (~15 minutes) for those covered assets."
        )
        next_steps.append(
            "After findings appear under Vulnerabilities, promote high/critical items to "
            "customer-visible recommendations."
        )
        entitlements_updated = True
    elif service_key in (
        "network_traffic_analysis",
        "threat_intelligence",
        "endpoint_forensics",
        "security_automation",
    ):
        current_ent = _fetch_entitlements(UUID(tenant_id)) or dict(DEFAULTS)
        merged = {
            **DEFAULTS,
            **{k: current_ent.get(k) for k in DEFAULTS if k in current_ent},
        }
        if service_key == "network_traffic_analysis":
            merged["zeek_enabled"] = True
            next_steps.append(
                "Network monitoring is now entitled. Complete sensor onboarding for this customer "
                "before traffic analytics appear."
            )
        elif service_key == "threat_intelligence":
            merged["misp_enabled"] = True
            next_steps.append(
                "Threat intelligence is now entitled. Confirm feed sharing scope with the customer."
            )
        elif service_key == "endpoint_forensics":
            merged["velociraptor_enabled"] = True
            next_steps.append(
                "Endpoint forensics is now entitled. Deploy collectors only after change approval."
            )
        elif service_key == "security_automation":
            merged["shuffle_mode"] = "standard"
            next_steps.append(
                "Security automation is now entitled. Review playbooks before enabling auto-actions."
            )
        upsert_tenant_entitlements(
            tenant_id,
            merged,
            actor_user_id=current_user.get("id"),
        )
        if chosen_ids:
            replace_coverage(
                tenant_id=tenant_id,
                service_key=service_key,
                asset_ids=chosen_ids,
                actor_user_id=current_user.get("id"),
            )
        entitlements_updated = True
        next_steps.append(
            "Customer will see this service as Active on Services after their next portal refresh."
        )
    else:
        entitlements_updated = False
        next_steps.append(
            "This service type is not auto-provisioned. Enable entitlements manually "
            "under Customers → Change Subscription."
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
        details={
            "service_key": service_key,
            "covered_asset_count": covered_count or len(chosen_ids),
        },
    )

    labels = {
        "vulnerability_management": "Vulnerability Management",
        "network_traffic_analysis": "Network monitoring",
        "threat_intelligence": "Threat intelligence",
        "endpoint_forensics": "Endpoint forensics",
        "security_automation": "Security automation",
    }
    label = labels.get(service_key, "Service")

    return {
        "request": _row_to_upgrade({**existing, "status": "accepted"}).model_dump(),
        "entitlements_updated": entitlements_updated,
        "covered_asset_ids": chosen_ids if service_key == "vulnerability_management" else [],
        "covered_count": covered_count,
        "message": (
            f"{label} is now enabled for this customer"
            + (
                f" on {covered_count} selected asset(s)."
                if service_key == "vulnerability_management"
                else ". They will see the active service on their next portal refresh."
            )
            if entitlements_updated
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
            updated_at::text,
            requested_asset_ids;
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


@router.get("/admin/tenants/{tenant_id}/asset-service-coverage")
def get_admin_asset_service_coverage(
    tenant_id: UUID,
    service_key: str = "vulnerability_management",
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    tenant = fetch_one(
        "SELECT id::text FROM tenants WHERE id = %s::uuid;",
        (str(tenant_id),),
    )
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return coverage_picker_payload(str(tenant_id), service_key)


@router.put("/admin/tenants/{tenant_id}/asset-service-coverage")
def put_admin_asset_service_coverage(
    tenant_id: UUID,
    payload: AssetCoveragePut,
    request: Request,
    current_user: Dict[str, Any] = Depends(require_roles("platform_admin", "soc_manager")),
) -> Dict[str, Any]:
    """
    Proactive / post-contract enable: set which assets are covered by a service.
    For Vulnerability Management, also flips the tenant entitlement on when enable_entitlement.
    """
    tenant = fetch_one(
        "SELECT id::text, name, short_code FROM tenants WHERE id = %s::uuid;",
        (str(tenant_id),),
    )
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    asset_ids = [str(x) for x in payload.asset_ids]
    if payload.service_key == "vulnerability_management" and payload.enable_entitlement and not asset_ids:
        raise HTTPException(
            status_code=422,
            detail="Select at least one asset for Vulnerability Management coverage.",
        )

    cov = replace_coverage(
        tenant_id=str(tenant_id),
        service_key=payload.service_key,
        asset_ids=asset_ids,
        actor_user_id=current_user.get("id"),
    )

    entitlements_updated = False
    if payload.service_key == "vulnerability_management" and payload.enable_entitlement:
        current_ent = _fetch_entitlements(tenant_id) or dict(DEFAULTS)
        cadence = payload.greenbone_cadence or current_ent.get("greenbone_cadence") or "monthly"
        if cadence == "off":
            cadence = "monthly"
        merged = {
            **DEFAULTS,
            **{k: current_ent.get(k) for k in DEFAULTS if k in current_ent},
            "greenbone_enabled": True,
            "greenbone_cadence": cadence,
        }
        upsert_tenant_entitlements(
            str(tenant_id),
            merged,
            actor_user_id=current_user.get("id"),
        )
        entitlements_updated = True

    write_audit_event(
        action="asset_service_coverage.updated",
        entity_type="tenant",
        entity_id=str(tenant_id),
        tenant_id=str(tenant_id),
        actor_user_id=current_user.get("id"),
        source_ip=request.client.host if request.client else None,
        details={
            "service_key": payload.service_key,
            "covered_count": cov.get("covered_count"),
            "entitlements_updated": entitlements_updated,
        },
    )

    picker = coverage_picker_payload(str(tenant_id), payload.service_key)
    return {
        **picker,
        "entitlements_updated": entitlements_updated,
        "message": (
            f"Coverage saved for {cov.get('covered_count', 0)} asset(s)."
            + (" Vulnerability Management entitlement enabled." if entitlements_updated else "")
        ),
    }

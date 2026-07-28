"""
KB-013: Admin Tenant Management API Foundation.
KB-072: On create/reprovision, auto-bind Wazuh agent group + TheHive org/tag.
KB-075: Contract-ready onboarding — commercial fields, entitlements, portal admin.
"""

from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from psycopg.errors import UniqueViolation

from app.api.dependencies import require_roles
from app.api.routes.admin import ADMIN_SOC_ROLES
from app.api.routes.entitlements import DEFAULTS as ENTITLEMENT_DEFAULTS
from app.api.routes.entitlements import upsert_tenant_entitlements
from app.core.security import hash_password
from app.db.session import fetch_one, fetch_one_write
from app.schemas.tenants import (
    DEFAULT_CREATE_ENTITLEMENTS,
    OnboardResult,
    TenantCreateRequest,
    TenantDetail,
    TenantEngineBinding,
    TenantUpdateRequest,
)
from app.services.tenant_engine_provisioner import (
    backfill_all_tenants,
    get_binding,
    provision_tenant_engines,
)

router = APIRouter(prefix="/admin/tenants", tags=["admin-tenants"])

ADMIN_TENANT_WRITE_ROLES = ("platform_admin",)

_COMMERCIAL_FIELDS = (
    "legal_name",
    "tax_id",
    "contract_reference",
    "contract_start_date",
    "contract_end_date",
    "licensed_endpoints",
    "data_residency",
    "preferred_language",
    "company_size",
)


def _fetch_entitlements_row(tenant_id: str) -> Optional[Dict[str, Any]]:
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
        WHERE tenant_id = %s::uuid;
        """,
        (tenant_id,),
    )


def _fetch_tenant_detail(tenant_id: UUID) -> Optional[Dict[str, Any]]:
    row = fetch_one(
        """
        SELECT
            t.id::text,
            t.name,
            t.short_code,
            t.status,
            t.sla_level,
            t.business_criticality,
            t.timezone,
            t.notes,
            t.deployment_mode,
            t.cloud_provider,
            t.primary_contact_name,
            t.primary_contact_email,
            t.primary_contact_phone,
            t.secondary_contact_name,
            t.secondary_contact_email,
            t.secondary_contact_phone,
            t.billing_email,
            t.address_line1,
            t.address_line2,
            t.city,
            t.state_region,
            t.postal_code,
            t.country,
            t.website,
            t.industry,
            t.legal_name,
            t.tax_id,
            t.contract_reference,
            t.contract_start_date::text,
            t.contract_end_date::text,
            t.licensed_endpoints,
            t.data_residency,
            t.preferred_language,
            t.company_size,
            t.created_at::text,
            t.updated_at::text,
            count(DISTINCT a.id) AS appliances,
            count(DISTINCT pa.id) AS protected_assets,
            count(DISTINCT i.id) AS incidents
        FROM tenants t
        LEFT JOIN appliances a ON a.tenant_id = t.id
        LEFT JOIN protected_assets pa ON pa.tenant_id = t.id
        LEFT JOIN incidents i ON i.tenant_id = t.id
        WHERE t.id = %s
        GROUP BY t.id;
        """,
        (str(tenant_id),),
    )
    if not row:
        return None
    binding = get_binding(str(tenant_id))
    row["engine_binding"] = binding or None
    ents = _fetch_entitlements_row(str(tenant_id))
    row["entitlements"] = ents or {"tenant_id": str(tenant_id), **ENTITLEMENT_DEFAULTS}
    return row


def _build_service_readiness(
    entitlements: Dict[str, Any], binding: Optional[Dict[str, Any]]
) -> Dict[str, str]:
    binding = binding or {}
    readiness: Dict[str, str] = {}
    if entitlements.get("wazuh_siem"):
        readiness["siem_log_management"] = binding.get("wazuh_group_status") or "pending"
    else:
        readiness["siem_log_management"] = "not_contracted"
    if entitlements.get("thehive_mode") and entitlements.get("thehive_mode") != "off":
        readiness["incident_response"] = binding.get("thehive_org_status") or "pending"
    else:
        readiness["incident_response"] = "not_contracted"
    if entitlements.get("shuffle_mode") and entitlements.get("shuffle_mode") != "off":
        readiness["security_automation"] = "queued"
    else:
        readiness["security_automation"] = "not_contracted"
    if entitlements.get("greenbone_enabled"):
        readiness["vulnerability_management"] = "queued"
    else:
        readiness["vulnerability_management"] = "not_contracted"
    readiness["network_traffic_analysis"] = (
        "queued" if entitlements.get("zeek_enabled") else "not_contracted"
    )
    readiness["threat_intelligence"] = (
        "queued" if entitlements.get("misp_enabled") else "not_contracted"
    )
    readiness["endpoint_forensics"] = (
        "queued" if entitlements.get("velociraptor_enabled") else "not_contracted"
    )
    return readiness


def _create_portal_admin(
    *,
    tenant_id: str,
    email: str,
    full_name: str,
    password: str,
    phone: Optional[str],
) -> Dict[str, Any]:
    existing = fetch_one(
        "SELECT id::text FROM platform_users WHERE lower(email) = lower(%s);",
        (email,),
    )
    if existing:
        raise ValueError(f"A user with email {email} already exists")
    password_hash = hash_password(password)
    row = fetch_one_write(
        """
        INSERT INTO platform_users (
            tenant_id, user_type, role, full_name, email, phone, status, password_hash
        )
        VALUES (%s::uuid, 'customer', 'customer_admin', %s, %s, %s, 'active', %s)
        RETURNING id::text, email, full_name, role;
        """,
        (tenant_id, full_name, email, phone, password_hash),
    )
    if not row:
        raise ValueError("Portal admin create failed")
    return row


@router.post("/engine-provision/backfill")
def backfill_engine_bindings(
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_TENANT_WRITE_ROLES)),
) -> Dict[str, Any]:
    """Provision / refresh engine bindings for all existing tenants."""
    result = backfill_all_tenants(actor_user_id=current_user.get("id"))
    return {
        "count": result["count"],
        "message": f"Provisioned/refreshed {result['count']} tenant engine binding(s).",
    }


@router.get("/{tenant_id}", response_model=TenantDetail)
def get_tenant_detail(
    tenant_id: UUID,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    tenant = _fetch_tenant_detail(tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return tenant


@router.get("/{tenant_id}/engine-binding", response_model=TenantEngineBinding)
def get_tenant_engine_binding(
    tenant_id: UUID,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    tenant = fetch_one("SELECT id::text FROM tenants WHERE id = %s::uuid;", (str(tenant_id),))
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    binding = get_binding(str(tenant_id))
    if not binding:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Engine binding not found — run provision",
        )
    return binding


@router.post("/{tenant_id}/engine-provision", response_model=TenantEngineBinding)
def reprovision_tenant_engines(
    tenant_id: UUID,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_TENANT_WRITE_ROLES)),
) -> Dict[str, Any]:
    tenant = fetch_one(
        "SELECT id::text, short_code, name FROM tenants WHERE id = %s::uuid;",
        (str(tenant_id),),
    )
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    binding = provision_tenant_engines(
        tenant_id=tenant["id"],
        short_code=tenant["short_code"],
        tenant_name=tenant["name"],
        actor_user_id=current_user.get("id"),
    )
    if not binding:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Engine provision failed",
        )
    return binding


@router.post("", response_model=TenantDetail, status_code=status.HTTP_201_CREATED)
def create_tenant(
    payload: TenantCreateRequest,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_TENANT_WRITE_ROLES)),
) -> Dict[str, Any]:
    existing = fetch_one(
        "SELECT id FROM tenants WHERE short_code = %s;",
        (payload.short_code,),
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A tenant with this short_code already exists",
        )

    try:
        created = fetch_one_write(
            """
            INSERT INTO tenants (
                name, short_code, status, sla_level, business_criticality,
                timezone, notes, deployment_mode, cloud_provider,
                primary_contact_name, primary_contact_email, primary_contact_phone,
                secondary_contact_name, secondary_contact_email, secondary_contact_phone,
                billing_email, address_line1, address_line2, city, state_region,
                postal_code, country, website, industry,
                legal_name, tax_id, contract_reference,
                contract_start_date, contract_end_date, licensed_endpoints,
                data_residency, preferred_language, company_size
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s::date, %s::date, %s, %s, %s, %s
            )
            RETURNING id::text;
            """,
            (
                payload.name,
                payload.short_code,
                payload.status,
                payload.sla_level,
                payload.business_criticality,
                payload.timezone,
                payload.notes,
                payload.deployment_mode,
                payload.cloud_provider,
                payload.primary_contact_name,
                payload.primary_contact_email,
                payload.primary_contact_phone,
                payload.secondary_contact_name,
                payload.secondary_contact_email,
                payload.secondary_contact_phone,
                payload.billing_email,
                payload.address_line1,
                payload.address_line2,
                payload.city,
                payload.state_region,
                payload.postal_code,
                payload.country,
                payload.website,
                payload.industry,
                payload.legal_name,
                payload.tax_id,
                payload.contract_reference,
                payload.contract_start_date,
                payload.contract_end_date,
                payload.licensed_endpoints,
                payload.data_residency,
                payload.preferred_language or "en",
                payload.company_size,
            ),
        )
    except UniqueViolation:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A tenant with this short_code already exists",
        )

    tenant_id = created["id"]
    ent_payload = (
        payload.entitlements.model_dump()
        if payload.entitlements
        else dict(DEFAULT_CREATE_ENTITLEMENTS)
    )
    entitlements_saved = False
    try:
        upsert_tenant_entitlements(
            tenant_id,
            ent_payload,
            actor_user_id=current_user.get("id"),
        )
        entitlements_saved = True
    except Exception:
        # Tenant remains; operator can set entitlements via Change Subscription
        pass

    binding: Optional[Dict[str, Any]] = None
    try:
        # Provision engines for contracted SIEM / IR (and always create binding row)
        should_provision = True
        if payload.entitlements:
            should_provision = bool(
                payload.entitlements.wazuh_siem
                or payload.entitlements.thehive_mode != "off"
            )
        if should_provision:
            binding = provision_tenant_engines(
                tenant_id=tenant_id,
                short_code=payload.short_code,
                tenant_name=payload.name,
                actor_user_id=current_user.get("id"),
            )
    except Exception:
        pass

    portal_created = False
    portal_email: Optional[str] = None
    portal_error: Optional[str] = None
    try:
        _create_portal_admin(
            tenant_id=tenant_id,
            email=payload.portal_admin.email,
            full_name=payload.portal_admin.full_name,
            password=payload.portal_admin.password,
            phone=payload.portal_admin.phone,
        )
        portal_created = True
        portal_email = payload.portal_admin.email
    except Exception as exc:
        # Portal login is part of onboard — surface failure clearly; tenant/engines remain.
        portal_error = str(exc)[:200]

    tenant = _fetch_tenant_detail(UUID(tenant_id))
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Tenant creation failed"
        )

    ents = tenant.get("entitlements") or ent_payload
    readiness = _build_service_readiness(ents, binding or tenant.get("engine_binding"))
    next_steps: List[str] = []
    if not portal_created:
        next_steps.append(
            "Portal admin was not created — fix the error above, then Users → Add User for this customer."
        )
    if payload.deployment_mode in ("cloud_appliance", "on_prem_appliance", "hybrid"):
        next_steps.append("Issue an Appliances activation token for the edge/onsite appliance.")
    else:
        next_steps.append(
            f"Enroll endpoints into Wazuh group "
            f"{(binding or tenant.get('engine_binding') or {}).get('wazuh_agent_group', 'tenant_' + payload.short_code)}."
        )
    if readiness.get("incident_response") == "tag_only":
        next_steps.append(
            "TheHive organisation create needs admin permission; tag-only mapping is active."
        )

    tenant["onboard_result"] = OnboardResult(
        entitlements_saved=entitlements_saved,
        portal_user_created=portal_created,
        portal_user_email=portal_email,
        portal_user_error=portal_error,
        service_readiness=readiness,
        next_steps=next_steps,
    ).model_dump()
    return tenant


@router.patch("/{tenant_id}", response_model=TenantDetail)
def update_tenant(
    tenant_id: UUID,
    payload: TenantUpdateRequest,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_TENANT_WRITE_ROLES)),
) -> Dict[str, Any]:
    existing = fetch_one(
        """
        SELECT deployment_mode, cloud_provider
        FROM tenants
        WHERE id = %s::uuid;
        """,
        (str(tenant_id),),
    )
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    updates: Dict[str, Any] = {}
    for field_name in (
        "name",
        "status",
        "sla_level",
        "business_criticality",
        "timezone",
        "notes",
        "primary_contact_name",
        "primary_contact_email",
        "primary_contact_phone",
        "secondary_contact_name",
        "secondary_contact_email",
        "secondary_contact_phone",
        "billing_email",
        "address_line1",
        "address_line2",
        "city",
        "state_region",
        "postal_code",
        "country",
        "website",
        "industry",
        "legal_name",
        "tax_id",
        "contract_reference",
        "contract_start_date",
        "contract_end_date",
        "licensed_endpoints",
        "data_residency",
        "preferred_language",
        "company_size",
    ):
        if field_name in payload.model_fields_set:
            updates[field_name] = getattr(payload, field_name)

    if payload.deployment_mode is not None or "cloud_provider" in payload.model_fields_set:
        from app.schemas.tenants import _normalize_cloud_provider, mode_allows_cloud_provider

        mode = payload.deployment_mode or existing["deployment_mode"]
        if "cloud_provider" in payload.model_fields_set:
            provider = payload.cloud_provider
        elif payload.deployment_mode is not None and not mode_allows_cloud_provider(
            payload.deployment_mode
        ):
            provider = None
        else:
            provider = existing.get("cloud_provider")
        try:
            provider = _normalize_cloud_provider(mode, provider)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc
        updates["deployment_mode"] = mode
        updates["cloud_provider"] = provider

    if not updates:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one field must be provided",
        )

    fields = [f"{key} = %s" for key in updates]
    params: list = list(updates.values())
    params.append(str(tenant_id))
    query = f"UPDATE tenants SET {', '.join(fields)} WHERE id = %s RETURNING id::text;"

    updated = fetch_one_write(query, tuple(params))
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    tenant = _fetch_tenant_detail(UUID(updated["id"]))
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Tenant update failed"
        )
    return tenant

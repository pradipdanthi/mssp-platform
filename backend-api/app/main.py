"""
KB-012: app/main.py is app wiring only - environment/app metadata, the
FastAPI app object, and router registration. All route logic (system,
admin, customer, auth) now lives under app/api/routes/.
"""

import os

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.admin import router as admin_router
from app.api.routes.admin_ops import router as admin_ops_router
from app.api.routes.alert_incident_triage import router as alert_incident_triage_router
from app.api.routes.appliance_agent import router as appliance_agent_router
from app.api.routes.appliance_channel import router as appliance_channel_router
from app.api.routes.appliance_alert_ingest import router as appliance_alert_ingest_router
from app.api.routes.appliance_management import router as appliance_management_router
from app.api.routes.telemetry_ingest import router as telemetry_ingest_router
from app.api.routes.auth import router as auth_router
from app.api.routes.customer import router as customer_router
from app.api.routes.health import router as health_router
from app.api.routes.on_prem_template import router as on_prem_template_router
from app.api.routes.recommendation_management import router as recommendation_management_router
from app.api.routes.soc_sync import router as soc_sync_router
from app.api.routes.tenant_management import router as tenant_management_router
from app.api.routes.user_management import router as user_management_router
from app.api.routes.admin_onboarding_configs import router as admin_onboarding_configs_router
from app.api.routes.admin_agent_packages import router as admin_agent_packages_router
from app.api.routes.delegated_user_management_v1 import router as delegated_user_management_v1_router
from app.api.routes.admin_customers_v1 import router as admin_customers_v1_router
from app.api.routes.audit_logs import (
    admin_router as audit_admin_router,
    customer_router as audit_customer_router,
    v1_admin_router as audit_v1_admin_router,
    v1_customer_router as audit_v1_customer_router,
)
from app.api.routes.customer_agent_packages import router as customer_agent_packages_router
from app.api.routes.public_agent_install import router as public_agent_install_router
from app.api.routes.customer_users import router as customer_users_router
from app.api.routes.edr import router as edr_router
from app.api.routes.entitlements import router as entitlements_router
from app.api.routes.service_catalog import router as service_catalog_router
from app.api.routes.compliance import router as compliance_router
from app.api.routes.easm import router as easm_router
from app.api.routes.easm_sync import router as easm_sync_router
from app.api.routes.itdr import router as itdr_router
from app.api.routes.vmaas import router as vmaas_router
from app.api.routes.ndr import router as ndr_router
from app.api.routes.threat_intel import router as threat_intel_router
from app.api.routes.threatlens import router as threatlens_router
from app.api.routes.endpoint_forensics import router as endpoint_forensics_router
from app.api.routes.vuln_sync import router as vuln_sync_router
from app.api.routes.vulnerability_management import router as vulnerability_management_router
from app.api.routes.admin_ai_chat import router as admin_ai_chat_router
from app.core.cors import get_cors_allowed_origins
from app.core.error_handlers import validation_exception_handler

APP_NAME = os.getenv("APP_NAME", "MSSP Control Plane API")
APP_ENV = os.getenv("APP_ENV", "development")

app = FastAPI(
    title=APP_NAME,
    description="Backend API foundation for the MSSP Control Plane.",
    version="0.1.0",
)

# Allow kevantic.com portal subdomains (admin / portal / marketing) plus lab LAN
# origins. Override with CORS_ALLOWED_ORIGINS in .env (comma-separated).
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_allowed_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Requested-With"],
)

# KB-014 fix: sanitize 422 validation-error responses globally so a
# whole-model validator error (e.g. UserCreateRequest's role/tenant_id
# check) can never echo a submitted password/new_password value back to the
# caller. See app/core/error_handlers.py for the full explanation. This
# changes response *content* only for errors that contain a sensitive key -
# the 422 status code and {"detail": [...]} shape are unchanged, and every
# other existing 422 response (e.g. KB-013's tenant validation errors) is
# unaffected.
app.add_exception_handler(RequestValidationError, validation_exception_handler)

# KB-010: auth/RBAC foundation. Public: POST /auth/login, GET /auth/roles.
# Protected: GET /auth/me.
app.include_router(auth_router)

# KB-012: system endpoints (public). Was inline in main.py through KB-011.
app.include_router(health_router)

# KB-011 protection (require_roles/get_current_user/require_tenant_match) is
# implemented inside these routers - see app/api/routes/admin.py and
# app/api/routes/customer.py. KB-012 only moved the route code out of
# main.py; it did not change any auth/RBAC/tenant-isolation behavior.
app.include_router(admin_router)
app.include_router(alert_incident_triage_router)
app.include_router(recommendation_management_router)
app.include_router(admin_ops_router)
app.include_router(customer_router)

# KB-013: admin tenant management (GET one, POST, PATCH) - adds alongside
# admin_router's existing GET /admin/tenants without modifying admin.py.
app.include_router(tenant_management_router)

# KB-014: admin user management (list, GET one, POST, PATCH, PATCH password).
app.include_router(user_management_router)

# KB-058: this static path must be registered before KB-015's dynamic
# /admin/appliances/{appliance_id} path so "on-prem-template" is not parsed
# as an appliance UUID.
app.include_router(on_prem_template_router)

# KB-015: admin appliance management (GET/PATCH one appliance, create/list/
# revoke appliance activation tokens for a tenant).
app.include_router(appliance_management_router)

# KB-016: appliance-facing registration and heartbeat receiver (no human
# JWT/RBAC - authenticated by activation token / durable appliance API key
# instead, see app/api/routes/appliance_agent.py).
app.include_router(appliance_agent_router)

# KB-093 Track-4: appliance channel (WSS + HTTPS poll) — temporary on control plane;
# production cutover moves this to Appliance Management plane.
app.include_router(appliance_channel_router)

# KB-057: authenticated appliance alert ingestion with normalized safe fields.
app.include_router(appliance_alert_ingest_router)

# KB-093E: Kevantic Edge telemetry ingest + hunt-result callback
# (/api/v1/telemetry/*). Same appliance API-key auth; may move to Appliance
# Management plane in production.
app.include_router(telemetry_ingest_router)

# KB-061: Shuffle/TheHive → control plane normalized sync (X-SOC-Sync-Key).
app.include_router(soc_sync_router)

# KB-069: Greenbone → control plane vulnerability ingest + admin management.
app.include_router(vuln_sync_router)
app.include_router(easm_sync_router)
app.include_router(vulnerability_management_router)

# KB-071: tenant entitlements + audit event write.
app.include_router(entitlements_router)
app.include_router(service_catalog_router)
app.include_router(compliance_router)
app.include_router(easm_router)
app.include_router(itdr_router)
app.include_router(vmaas_router)
app.include_router(ndr_router)
app.include_router(threat_intel_router)
app.include_router(threatlens_router)
app.include_router(endpoint_forensics_router)
app.include_router(edr_router)

# KB-096: Admin AI chat (SOC Q&A; dark behind AI_CHAT_ENABLED).
app.include_router(admin_ai_chat_router)

# KB-084: endpoint onboarding config packages (Sysmon/Osquery templates).
app.include_router(admin_onboarding_configs_router)

# KB-086: per-tenant agent install packages (Windows/Linux) + public Linux one-liner.
app.include_router(admin_agent_packages_router)
app.include_router(customer_agent_packages_router)
app.include_router(public_agent_install_router)

# KB-085: customer user mgmt, audit logs, v1 customer onboarding alias.
app.include_router(customer_users_router)
app.include_router(audit_admin_router)
app.include_router(audit_customer_router)
app.include_router(audit_v1_admin_router)
app.include_router(audit_v1_customer_router)
app.include_router(admin_customers_v1_router)
app.include_router(delegated_user_management_v1_router)


# ---------------------------------------------------------------------------
# Background tasks
# ---------------------------------------------------------------------------
import asyncio
from app.services.edr_sweeper import edr_sweeper_loop
from app.services.shuffle_retry_queue import start_shuffle_retry_worker
from app.services.ai_alert_queue import start_ai_alert_worker

_sweeper_task = None

@app.on_event("startup")
async def _start_background_tasks():
    global _sweeper_task
    _sweeper_task = asyncio.create_task(edr_sweeper_loop())
    start_shuffle_retry_worker()
    start_ai_alert_worker()

@app.on_event("shutdown")
async def _stop_background_tasks():
    if _sweeper_task:
        _sweeper_task.cancel()

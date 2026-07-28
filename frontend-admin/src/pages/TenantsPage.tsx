import { FormEvent, useMemo, useRef, useState } from "react";
import {
  Tenant,
  TenantCloudProvider,
  TenantCreateRequest,
  TenantCriticality,
  TenantDeploymentMode,
  TenantSlaLevel,
  TenantStatus,
  createTenant,
  getTenantDetail,
  getTenantEngineBinding,
  getTenants,
  postAuditEvent,
  provisionTenantEngines,
  backfillTenantEngineBindings,
  updateTenant,
  type TenantEngineBinding,
} from "../api/admin";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import ConfirmDangerModal from "../components/ConfirmDangerModal";
import CreateEntitlementsFields, {
  CreateEntitlementsState,
} from "../components/CreateEntitlementsFields";
import RowActionsMenu from "../components/RowActionsMenu";
import SubscriptionEntitlementsPanel from "../components/SubscriptionEntitlementsPanel";
import {
  COMPANY_SIZE_OPTIONS,
  DATA_RESIDENCY_OPTIONS,
  DEFAULT_CREATE_ENTITLEMENTS,
  INDUSTRY_OPTIONS,
  PREFERRED_LANGUAGE_OPTIONS,
} from "../data/contractOptions";
import { COUNTRY_OPTIONS, getTimezoneOptions } from "../data/geoOptions";
import { useAdminQuery } from "../hooks/useAdminQuery";

const TIMEZONE_OPTIONS = getTimezoneOptions();

const STATUS_OPTIONS: TenantStatus[] = ["onboarding", "active", "inactive", "suspended"];
const SLA_OPTIONS: TenantSlaLevel[] = ["standard", "business", "premium", "24x7"];
const CRITICALITY_OPTIONS: TenantCriticality[] = ["low", "medium", "high", "critical"];
const DEPLOYMENT_MODE_OPTIONS: { value: TenantDeploymentMode; label: string; hint: string }[] = [
  {
    value: "cloud",
    label: "Cloud without appliance",
    hint: "Customer estate in AWS / Azure / GCP — agents feed MSSP cloud SOC directly (no edge box).",
  },
  {
    value: "cloud_appliance",
    label: "Cloud with appliance",
    hint: "Cloud workloads, plus an onsite/edge appliance that forwards only allowed metadata to the MSSP.",
  },
  {
    value: "on_prem_direct",
    label: "On-prem without appliance",
    hint: "Customer is on-premises; agents talk to MSSP cloud (no edge box).",
  },
  {
    value: "on_prem_appliance",
    label: "On-prem with appliance",
    hint: "Edge appliance on site — only safe metadata reaches the cloud.",
  },
  {
    value: "hybrid",
    label: "Hybrid",
    hint: "Mix of cloud path and on-prem appliance under one customer.",
  },
];
const CLOUD_PROVIDER_OPTIONS: TenantCloudProvider[] = ["aws", "azure", "gcp", "other"];

function deploymentModeLabel(mode: string | undefined): string {
  return DEPLOYMENT_MODE_OPTIONS.find((o) => o.value === mode)?.label ?? mode ?? "—";
}

function needsCloudProvider(mode: TenantDeploymentMode): boolean {
  return mode === "cloud" || mode === "cloud_appliance" || mode === "hybrid";
}

function requiresCloudProviderStrict(mode: TenantDeploymentMode): boolean {
  return mode === "cloud" || mode === "cloud_appliance";
}

/** Derive a stable short_code candidate from a company name (uppercase A-Z0-9_-). */
function suggestShortCodeFromName(name: string): string {
  const cleaned = name
    .trim()
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .replace(/_+/g, "_");
  if (!cleaned) return "";
  // Prefer compact codes: drop tiny filler tokens when possible
  const parts = cleaned
    .split("_")
    .filter((p) => p.length > 0 && !["THE", "AND", "OF", "PVT", "LTD", "LLC", "INC"].includes(p));
  const base = (parts.length ? parts.join("_") : cleaned).slice(0, 20);
  return base.length >= 2 ? base : cleaned.slice(0, 20).padEnd(2, "X");
}

/** Random A-Z0-9 suffix for uniqueness (always appended on auto-generate). */
function randomCodeSuffix(length = 4): string {
  const alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"; // no I/O/0/1 — easier to read
  let out = "";
  for (let i = 0; i < length; i++) {
    out += alphabet[Math.floor(Math.random() * alphabet.length)];
  }
  return out;
}

/**
 * Auto short code = NAME_PREFIX + alphanumeric suffix (e.g. MELVIK-K7M2).
 * Always unique-looking; also checked against existing tenants.
 */
function autoShortCodeFromName(name: string, taken: Set<string>): string {
  const raw = suggestShortCodeFromName(name);
  const prefix = (raw || "CUST").replace(/_+/g, "").slice(0, 12) || "CUST";
  for (let attempt = 0; attempt < 40; attempt++) {
    const suffix = randomCodeSuffix(4);
    // Prefer hyphen form; fall back to compact if over 20 chars
    let code = `${prefix}-${suffix}`;
    if (code.length > 20) {
      code = `${prefix.slice(0, 15)}${suffix}`.slice(0, 20);
    }
    if (!taken.has(code)) return code;
  }
  return ensureUniqueShortCode(`${prefix}-${randomCodeSuffix(4)}`.slice(0, 20), taken);
}

function ensureUniqueShortCode(candidate: string, taken: Set<string>): string {
  let code = candidate.slice(0, 20);
  if (code.length < 2) code = "CUST";
  if (!taken.has(code)) return code;
  for (let i = 2; i < 1000; i++) {
    const suffix = String(i);
    const next = `${code.slice(0, Math.max(2, 20 - suffix.length))}${suffix}`;
    if (!taken.has(next)) return next;
  }
  const rand = randomCodeSuffix(5);
  return `T${rand}`.slice(0, 20);
}

function randomShortCode(taken: Set<string>): string {
  for (let attempt = 0; attempt < 50; attempt++) {
    const code = `T-${randomCodeSuffix(6)}`.slice(0, 20);
    if (!taken.has(code)) return code;
  }
  return `T-${Date.now().toString(36).toUpperCase()}`.slice(0, 20);
}

function apiErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    if (typeof err.detail === "string") return err.detail;
    if (err.status === 403) return "Access denied. Only platform_admin can create or edit customers.";
    if (err.status === 409) return "A customer with this short code already exists.";
  }
  return fallback;
}

type CreateFormState = {
  name: string;
  short_code: string;
  status: TenantStatus;
  sla_level: TenantSlaLevel;
  business_criticality: TenantCriticality;
  timezone: string;
  notes: string;
  deployment_mode: TenantDeploymentMode;
  cloud_provider: TenantCloudProvider | "";
  primary_contact_name: string;
  primary_contact_email: string;
  primary_contact_phone: string;
  secondary_contact_name: string;
  secondary_contact_email: string;
  secondary_contact_phone: string;
  billing_email: string;
  address_line1: string;
  address_line2: string;
  city: string;
  state_region: string;
  postal_code: string;
  country: string;
  website: string;
  industry: string;
  legal_name: string;
  tax_id: string;
  contract_reference: string;
  contract_start_date: string;
  contract_end_date: string;
  licensed_endpoints: string;
  data_residency: string;
  preferred_language: string;
  company_size: string;
  create_portal_admin: boolean;
  portal_admin_email: string;
  portal_admin_full_name: string;
  portal_admin_password: string;
  portal_admin_phone: string;
  entitlements: CreateEntitlementsState;
};

type EditFormState = {
  name: string;
  status: TenantStatus;
  sla_level: TenantSlaLevel;
  business_criticality: TenantCriticality;
  timezone: string;
  notes: string;
  deployment_mode: TenantDeploymentMode;
  cloud_provider: TenantCloudProvider | "";
  primary_contact_name: string;
  primary_contact_email: string;
  primary_contact_phone: string;
  secondary_contact_name: string;
  secondary_contact_email: string;
  secondary_contact_phone: string;
  billing_email: string;
  address_line1: string;
  address_line2: string;
  city: string;
  state_region: string;
  postal_code: string;
  country: string;
  website: string;
  industry: string;
  legal_name: string;
  tax_id: string;
  contract_reference: string;
  contract_start_date: string;
  contract_end_date: string;
  licensed_endpoints: string;
  data_residency: string;
  preferred_language: string;
  company_size: string;
};

const EMPTY_CREATE: CreateFormState = {
  name: "",
  short_code: "",
  status: "active",
  sla_level: "standard",
  business_criticality: "medium",
  timezone: "Asia/Kolkata",
  notes: "",
  deployment_mode: "cloud",
  cloud_provider: "aws",
  primary_contact_name: "",
  primary_contact_email: "",
  primary_contact_phone: "",
  secondary_contact_name: "",
  secondary_contact_email: "",
  secondary_contact_phone: "",
  billing_email: "",
  address_line1: "",
  address_line2: "",
  city: "",
  state_region: "",
  postal_code: "",
  country: "",
  website: "",
  industry: "",
  legal_name: "",
  tax_id: "",
  contract_reference: "",
  contract_start_date: "",
  contract_end_date: "",
  licensed_endpoints: "",
  data_residency: "India",
  preferred_language: "en",
  company_size: "",
  create_portal_admin: true,
  portal_admin_email: "",
  portal_admin_full_name: "",
  portal_admin_password: "",
  portal_admin_phone: "",
  entitlements: { ...DEFAULT_CREATE_ENTITLEMENTS, roadmap_notes: "" },
};

function profilePayloadFromForm(form: CreateFormState | EditFormState) {
  const blank = (v: string) => (v.trim() ? v.trim() : null);
  const endpoints = form.licensed_endpoints.trim();
  return {
    primary_contact_name: form.primary_contact_name.trim(),
    primary_contact_email: form.primary_contact_email.trim(),
    primary_contact_phone: blank(form.primary_contact_phone),
    secondary_contact_name: blank(form.secondary_contact_name),
    secondary_contact_email: blank(form.secondary_contact_email),
    secondary_contact_phone: blank(form.secondary_contact_phone),
    billing_email: blank(form.billing_email),
    address_line1: blank(form.address_line1),
    address_line2: blank(form.address_line2),
    city: blank(form.city),
    state_region: blank(form.state_region),
    postal_code: blank(form.postal_code),
    country: form.country.trim(),
    website: blank(form.website),
    industry: blank(form.industry),
    legal_name: blank(form.legal_name),
    tax_id: blank(form.tax_id),
    contract_reference: blank(form.contract_reference),
    contract_start_date: blank(form.contract_start_date),
    contract_end_date: blank(form.contract_end_date),
    licensed_endpoints: endpoints ? Number(endpoints) : null,
    data_residency: blank(form.data_residency),
    preferred_language: blank(form.preferred_language) || "en",
    company_size: blank(form.company_size),
  };
}

export default function TenantsPage() {
  const { user } = useAuth();
  const canWrite = user?.role === "platform_admin";
  const { status, data, errorMessage, refetch } = useAdminQuery(() => getTenants(), []);

  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState<CreateFormState>(EMPTY_CREATE);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [createSuccess, setCreateSuccess] = useState<string | null>(null);

  const [editing, setEditing] = useState<Tenant | null>(null);
  const [editForm, setEditForm] = useState<EditFormState | null>(null);
  const [saving, setSaving] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const [editSuccess, setEditSuccess] = useState<string | null>(null);
  const editPanelRef = useRef<HTMLFormElement | null>(null);

  const [subscriptionTenant, setSubscriptionTenant] = useState<Tenant | null>(null);
  const [engineBinding, setEngineBinding] = useState<TenantEngineBinding | null>(null);
  const [engineTenant, setEngineTenant] = useState<Tenant | null>(null);
  const [engineBusy, setEngineBusy] = useState(false);
  const [offboardTenant, setOffboardTenant] = useState<Tenant | null>(null);
  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [modeFilter, setModeFilter] = useState<TenantDeploymentMode | "all">("all");
  /** When false, short_code follows customer name; when true, admin overrode it. */
  const [shortCodeManual, setShortCodeManual] = useState(false);

  const takenShortCodes = useMemo(() => {
    const set = new Set<string>();
    for (const t of data?.tenants ?? []) {
      if (t.short_code) set.add(t.short_code.toUpperCase());
    }
    return set;
  }, [data?.tenants]);

  const filteredTenants = useMemo(() => {
    const list = data?.tenants ?? [];
    if (modeFilter === "all") return list;
    return list.filter((t) => t.deployment_mode === modeFilter);
  }, [data?.tenants, modeFilter]);

  function openCreate() {
    setCreateForm(EMPTY_CREATE);
    setShortCodeManual(false);
    setCreateError(null);
    setCreateSuccess(null);
    setShowCreate(true);
  }

  function onCreateNameChange(name: string) {
    if (shortCodeManual) {
      setCreateForm({ ...createForm, name });
      return;
    }
    const unique = name.trim() ? autoShortCodeFromName(name, takenShortCodes) : "";
    setCreateForm({ ...createForm, name, short_code: unique });
  }

  function onShortCodeChange(value: string) {
    setShortCodeManual(true);
    setCreateForm({ ...createForm, short_code: value.toUpperCase() });
  }

  function regenerateShortCode() {
    const next = createForm.name.trim()
      ? autoShortCodeFromName(createForm.name, takenShortCodes)
      : randomShortCode(takenShortCodes);
    setShortCodeManual(true);
    setCreateForm({ ...createForm, short_code: next });
  }

  function resetShortCodeAuto() {
    setShortCodeManual(false);
    const unique = createForm.name.trim()
      ? autoShortCodeFromName(createForm.name, takenShortCodes)
      : "";
    setCreateForm({ ...createForm, short_code: unique });
  }

  function openEdit(tenant: Tenant) {
    setShowCreate(false);
    setEditing(tenant);
    setEditForm({
      name: tenant.name,
      status: tenant.status as TenantStatus,
      sla_level: tenant.sla_level as TenantSlaLevel,
      business_criticality: tenant.business_criticality as TenantCriticality,
      timezone: tenant.timezone || "Asia/Kolkata",
      notes: "",
      deployment_mode: (tenant.deployment_mode || "cloud") as TenantDeploymentMode,
      cloud_provider: (tenant.cloud_provider || "") as TenantCloudProvider | "",
      primary_contact_name: tenant.primary_contact_name ?? "",
      primary_contact_email: tenant.primary_contact_email ?? "",
      primary_contact_phone: tenant.primary_contact_phone ?? "",
      secondary_contact_name: "",
      secondary_contact_email: "",
      secondary_contact_phone: "",
      billing_email: "",
      address_line1: "",
      address_line2: "",
      city: tenant.city ?? "",
      state_region: "",
      postal_code: "",
      country: tenant.country ?? "",
      website: "",
      industry: tenant.industry ?? "",
      legal_name: "",
      tax_id: "",
      contract_reference: tenant.contract_reference ?? "",
      contract_start_date: "",
      contract_end_date: "",
      licensed_endpoints: tenant.licensed_endpoints != null ? String(tenant.licensed_endpoints) : "",
      data_residency: "",
      preferred_language: "en",
      company_size: "",
    });
    setEditError(null);
    setEditSuccess(null);
    window.setTimeout(() => {
      editPanelRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 50);
    getTenantDetail(tenant.id)
      .then((detail) => {
        setEditForm({
          name: detail.name,
          status: detail.status as TenantStatus,
          sla_level: detail.sla_level as TenantSlaLevel,
          business_criticality: detail.business_criticality as TenantCriticality,
          timezone: detail.timezone || "Asia/Kolkata",
          notes: detail.notes ?? "",
          deployment_mode: (detail.deployment_mode || "cloud") as TenantDeploymentMode,
          cloud_provider: (detail.cloud_provider || "") as TenantCloudProvider | "",
          primary_contact_name: detail.primary_contact_name ?? "",
          primary_contact_email: detail.primary_contact_email ?? "",
          primary_contact_phone: detail.primary_contact_phone ?? "",
          secondary_contact_name: detail.secondary_contact_name ?? "",
          secondary_contact_email: detail.secondary_contact_email ?? "",
          secondary_contact_phone: detail.secondary_contact_phone ?? "",
          billing_email: detail.billing_email ?? "",
          address_line1: detail.address_line1 ?? "",
          address_line2: detail.address_line2 ?? "",
          city: detail.city ?? "",
          state_region: detail.state_region ?? "",
          postal_code: detail.postal_code ?? "",
          country: detail.country ?? "",
          website: detail.website ?? "",
          industry: detail.industry ?? "",
          legal_name: detail.legal_name ?? "",
          tax_id: detail.tax_id ?? "",
          contract_reference: detail.contract_reference ?? "",
          contract_start_date: (detail.contract_start_date || "").slice(0, 10),
          contract_end_date: (detail.contract_end_date || "").slice(0, 10),
          licensed_endpoints:
            detail.licensed_endpoints != null ? String(detail.licensed_endpoints) : "",
          data_residency: detail.data_residency ?? "",
          preferred_language: detail.preferred_language ?? "en",
          company_size: detail.company_size ?? "",
        });
      })
      .catch((err) => {
        setEditError(apiErrorMessage(err, "Could not load customer details for editing."));
      });
  }

  async function handleCreate(event: FormEvent) {
    event.preventDefault();
    if (!canWrite) return;
    setCreating(true);
    setCreateError(null);
    setCreateSuccess(null);
    if (requiresCloudProviderStrict(createForm.deployment_mode) && !createForm.cloud_provider) {
      setCreateError("Select a cloud provider (AWS, Azure, GCP, or Other).");
      setCreating(false);
      return;
    }
    if (!createForm.primary_contact_name.trim() || !createForm.primary_contact_email.trim()) {
      setCreateError("Primary contact name and email are required.");
      setCreating(false);
      return;
    }
    if (!createForm.country.trim()) {
      setCreateError("Country is required.");
      setCreating(false);
      return;
    }
    {
      const email = (createForm.portal_admin_email || createForm.primary_contact_email).trim();
      const fullName = (createForm.portal_admin_full_name || createForm.primary_contact_name).trim();
      if (!email || !fullName || createForm.portal_admin_password.trim().length < 8) {
        setCreateError(
          "Every customer onboard requires a portal admin: email, full name, and password (min 8 characters)."
        );
        setCreating(false);
        return;
      }
    }
    let shortCode = createForm.short_code.trim().toUpperCase();
    if (shortCode.length < 2) {
      shortCode = createForm.name.trim()
        ? autoShortCodeFromName(createForm.name, takenShortCodes)
        : randomShortCode(takenShortCodes);
    }
    const payload: TenantCreateRequest = {
      name: createForm.name.trim(),
      short_code: shortCode,
      status: createForm.status,
      sla_level: createForm.sla_level,
      business_criticality: createForm.business_criticality,
      timezone: createForm.timezone.trim() || "Asia/Kolkata",
      notes: createForm.notes.trim() || null,
      deployment_mode: createForm.deployment_mode,
      cloud_provider: needsCloudProvider(createForm.deployment_mode)
        ? createForm.cloud_provider || null
        : null,
      ...profilePayloadFromForm(createForm),
      entitlements: {
        ...createForm.entitlements,
        roadmap_notes: createForm.entitlements.roadmap_notes.trim() || null,
      },
      portal_admin: {
        email: (createForm.portal_admin_email || createForm.primary_contact_email).trim(),
        full_name: (createForm.portal_admin_full_name || createForm.primary_contact_name).trim(),
        password: createForm.portal_admin_password,
        phone: (createForm.portal_admin_phone || createForm.primary_contact_phone).trim() || null,
      },
    };
    try {
      const created = await createTenant(payload);
      void postAuditEvent({
        action: "tenant.created",
        entity_type: "tenant",
        entity_id: created.id,
        tenant_id: created.id,
        details: {
          after: {
            name: created.name,
            short_code: created.short_code,
            status: created.status,
            deployment_mode: created.deployment_mode,
            cloud_provider: created.cloud_provider,
            entitlements_saved: created.onboard_result?.entitlements_saved ?? false,
            portal_user_created: created.onboard_result?.portal_user_created ?? false,
          },
        },
      }).catch(() => undefined);
      const ob = created.onboard_result;
      const readiness = ob?.service_readiness
        ? Object.entries(ob.service_readiness)
            .map(([k, v]) => `${k}=${v}`)
            .join("; ")
        : "";
      const nextFromApi = ob?.next_steps?.length ? ` Next: ${ob.next_steps.join(" ")}` : "";
      setCreateSuccess(
        `Customer "${created.name}" (${created.short_code}) onboarded as ${deploymentModeLabel(created.deployment_mode)}.` +
          (created.engine_binding
            ? ` Engines: Wazuh ${created.engine_binding.wazuh_agent_group} (${created.engine_binding.wazuh_group_status}); TheHive ${created.engine_binding.thehive_org_status}.`
            : " Engine binding pending.") +
          (ob?.portal_user_created
            ? ` Portal admin created (${ob.portal_user_email}).`
            : ob?.portal_user_error
              ? ` Portal admin not created: ${ob.portal_user_error}.`
              : " No portal admin created.") +
          (readiness ? ` Service readiness: ${readiness}.` : "") +
          nextFromApi
      );
      setCreateForm(EMPTY_CREATE);
      setShowCreate(false);
      refetch();
    } catch (err) {
      setCreateError(apiErrorMessage(err, "Could not create customer."));
    } finally {
      setCreating(false);
    }
  }

  async function handleEdit(event: FormEvent) {
    event.preventDefault();
    if (!canWrite || !editing || !editForm) return;
    setSaving(true);
    setEditError(null);
    setEditSuccess(null);
    if (requiresCloudProviderStrict(editForm.deployment_mode) && !editForm.cloud_provider) {
      setEditError("Select a cloud provider (AWS, Azure, GCP, or Other).");
      setSaving(false);
      return;
    }
    if (!editForm.primary_contact_name.trim() || !editForm.primary_contact_email.trim()) {
      setEditError("Primary contact name and email are required.");
      setSaving(false);
      return;
    }
    if (!editForm.country.trim()) {
      setEditError("Country is required.");
      setSaving(false);
      return;
    }
    try {
      const beforeStatus = editing.status;
      const updated = await updateTenant(editing.id, {
        name: editForm.name.trim(),
        status: editForm.status,
        sla_level: editForm.sla_level,
        business_criticality: editForm.business_criticality,
        timezone: editForm.timezone.trim() || "Asia/Kolkata",
        notes: editForm.notes.trim() || null,
        deployment_mode: editForm.deployment_mode,
        cloud_provider: needsCloudProvider(editForm.deployment_mode)
          ? editForm.cloud_provider || null
          : null,
        ...profilePayloadFromForm(editForm),
      });
      void postAuditEvent({
        action: "tenant.updated",
        entity_type: "tenant",
        entity_id: updated.id,
        tenant_id: updated.id,
        details: {
          before: { status: beforeStatus, name: editing.name, deployment_mode: editing.deployment_mode },
          after: {
            status: updated.status,
            name: updated.name,
            deployment_mode: updated.deployment_mode,
            cloud_provider: updated.cloud_provider,
          },
        },
      }).catch(() => undefined);
      setEditSuccess(`Saved changes for ${updated.name} (${updated.short_code}).`);
      setEditing(null);
      setEditForm(null);
      refetch();
    } catch (err) {
      setEditError(apiErrorMessage(err, "Could not update customer."));
    } finally {
      setSaving(false);
    }
  }

  async function suspendTenant(tenant: Tenant) {
    if (!canWrite || actionBusy) return;
    setActionBusy(true);
    setActionError(null);
    try {
      const updated = await updateTenant(tenant.id, { status: "suspended" });
      void postAuditEvent({
        action: "tenant.suspended",
        entity_type: "tenant",
        entity_id: tenant.id,
        tenant_id: tenant.id,
        details: { before: { status: tenant.status }, after: { status: updated.status } },
      }).catch(() => undefined);
      setEditSuccess(`Suspended ${updated.name}. Access and ingestion stay frozen; data is kept.`);
      refetch();
    } catch (err) {
      setActionError(apiErrorMessage(err, "Could not suspend customer."));
    } finally {
      setActionBusy(false);
    }
  }

  async function showEngineBinding(tenant: Tenant) {
    setActionError(null);
    setEngineTenant(tenant);
    try {
      const binding = await getTenantEngineBinding(tenant.id);
      setEngineBinding(binding);
    } catch {
      if (!canWrite) {
        setActionError("No engine binding for this customer yet.");
        return;
      }
      await runProvision(tenant);
    }
  }

  async function runProvision(tenant: Tenant) {
    if (!canWrite || engineBusy) return;
    setEngineBusy(true);
    setActionError(null);
    setEngineTenant(tenant);
    try {
      const binding = await provisionTenantEngines(tenant.id);
      setEngineBinding(binding);
      setEditSuccess(
        `Engine provision refreshed for ${tenant.short_code}: Wazuh ${binding.wazuh_group_status}, TheHive ${binding.thehive_org_status}.`
      );
      refetch();
    } catch (err) {
      setActionError(apiErrorMessage(err, "Could not provision engines for this customer."));
    } finally {
      setEngineBusy(false);
    }
  }

  async function runBackfill() {
    if (!canWrite || engineBusy) return;
    setEngineBusy(true);
    setActionError(null);
    try {
      const result = await backfillTenantEngineBindings();
      setEditSuccess(result.message);
      refetch();
    } catch (err) {
      setActionError(apiErrorMessage(err, "Could not backfill engine bindings."));
    } finally {
      setEngineBusy(false);
    }
  }

  async function offboardConfirmed() {
    if (!canWrite || !offboardTenant) return;
    const tenant = offboardTenant;
    setActionBusy(true);
    setActionError(null);
    try {
      const updated = await updateTenant(tenant.id, {
        status: "inactive",
        notes: `Offboarded via admin UI at ${new Date().toISOString()}`,
      });
      void postAuditEvent({
        action: "tenant.offboarded",
        entity_type: "tenant",
        entity_id: tenant.id,
        tenant_id: tenant.id,
        details: {
          before: { status: tenant.status, name: tenant.name },
          after: { status: updated.status, name: updated.name },
          mode: "archive_inactive",
        },
      }).catch(() => undefined);
      setOffboardTenant(null);
      setEditSuccess(
        `Offboarded ${updated.name}. Record archived as inactive (not hard-deleted).`
      );
      refetch();
    } catch (err) {
      setActionError(apiErrorMessage(err, "Could not offboard customer."));
    } finally {
      setActionBusy(false);
    }
  }

  return (
    <div>
      <div className="page-header-row">
        <div>
          <h1 className="page-title">Customers / Tenants</h1>
          <p className="page-subtitle">
            Every new customer is onboarded end-to-end from this page: organization profile,
            contracted services, backend engine slots, and the first portal login. Click a name to
            open details. Short codes are permanent identifiers used in portal URLs.
          </p>
        </div>
        {canWrite && (
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            <button className="btn btn-ghost" type="button" disabled={engineBusy} onClick={() => void runBackfill()}>
              {engineBusy ? "Provisioning…" : "Provision all engines"}
            </button>
            <button className="btn btn-primary" type="button" onClick={openCreate}>
              Add Customer
            </button>
          </div>
        )}
      </div>

      {!canWrite && (
        <div className="state-message" style={{ marginBottom: "1rem" }}>
          You can view customers. Creating or editing requires a platform_admin account.
        </div>
      )}

      {createSuccess && <div className="state-message state-success">{createSuccess}</div>}
      {editSuccess && <div className="state-message state-success">{editSuccess}</div>}
      {actionError && <div className="state-message state-error">{actionError}</div>}

      {subscriptionTenant && canWrite && (
        <SubscriptionEntitlementsPanel
          tenantId={subscriptionTenant.id}
          tenantName={`${subscriptionTenant.name} (${subscriptionTenant.short_code})`}
          onClose={() => setSubscriptionTenant(null)}
        />
      )}

      {engineBinding && (
        <div className="card-surface" style={{ marginBottom: "1rem", padding: "1rem" }}>
          <div className="page-header-row" style={{ marginBottom: "0.75rem" }}>
            <h2 className="page-title" style={{ fontSize: "1.05rem", margin: 0 }}>
              Engine binding
            </h2>
            <button className="btn btn-ghost" type="button" onClick={() => { setEngineBinding(null); setEngineTenant(null); }}>
              Close
            </button>
          </div>
          <p className="page-subtitle" style={{ marginTop: 0 }}>
            Enroll customer devices into the Wazuh agent group below. Alerts tagged with the TheHive
            tenant tag map back to this customer automatically.
          </p>
          <ul style={{ margin: 0, paddingLeft: "1.2rem", lineHeight: 1.6 }}>
            <li>
              <strong>Wazuh group:</strong> <code>{engineBinding.wazuh_agent_group}</code> —{" "}
              {engineBinding.wazuh_group_status}
              {engineBinding.wazuh_last_error ? ` (${engineBinding.wazuh_last_error})` : ""}
            </li>
            <li>
              <strong>TheHive org:</strong> <code>{engineBinding.thehive_org_name}</code> —{" "}
              {engineBinding.thehive_org_status}
              {engineBinding.thehive_last_error ? ` (${engineBinding.thehive_last_error})` : ""}
            </li>
            <li>
              <strong>TheHive tag:</strong> <code>{engineBinding.thehive_tenant_tag}</code>
            </li>
          </ul>
          {canWrite && engineTenant && (
            <button
              className="btn btn-primary"
              type="button"
              style={{ marginTop: "0.75rem" }}
              disabled={engineBusy}
              onClick={() => void runProvision(engineTenant)}
            >
              Retry provision
            </button>
          )}
        </div>
      )}

      <ConfirmDangerModal
        open={!!offboardTenant}
        title="Offboard customer"
        body={
          offboardTenant
            ? `This archives ${offboardTenant.name} as inactive. Data is retained for audit; portal access is frozen. Hard purge is not performed from this UI.`
            : ""
        }
        confirmPhrase={offboardTenant ? `DELETE ${offboardTenant.name}` : ""}
        confirmLabel="Offboard customer"
        onCancel={() => setOffboardTenant(null)}
        onConfirm={offboardConfirmed}
      />

      {showCreate && canWrite && (
        <form className="management-panel" onSubmit={handleCreate}>
          <h2 className="section-title" style={{ marginTop: 0 }}>
            Onboard new customer
          </h2>
          <p className="page-subtitle" style={{ marginBottom: "12px" }}>
            This is the standard path for every customer — not a special case.
            Completing this form creates the tenant, contracted service entitlements, backend tool
            bindings (SIEM / IR), and the first customer portal admin user.
          </p>
          <div className="form-grid">
            <label className="form-label">
              Customer name
              <input
                className="form-input"
                required
                maxLength={200}
                value={createForm.name}
                onChange={(e) => onCreateNameChange(e.target.value)}
              />
            </label>
            <label className="form-label">
              Short code (auto-generated — editable)
              <div className="short-code-row">
                <input
                  className="form-input"
                  required
                  minLength={2}
                  maxLength={20}
                  pattern="[A-Za-z0-9_-]+"
                  value={createForm.short_code}
                  onChange={(e) => onShortCodeChange(e.target.value)}
                  title="Used for Wazuh group tenant_<CODE> and engine bindings. Locked after create."
                />
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={regenerateShortCode}
                  title="Generate another unique code"
                >
                  Generate
                </button>
                {shortCodeManual && (
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={resetShortCodeAuto}
                    title="Follow customer name again"
                  >
                    Auto
                  </button>
                )}
              </div>
              <span className="muted-text">
                Auto format: <code>NAME-XXXX</code> (e.g. <code>MELVIK-K7M2</code>) → Wazuh group{" "}
                <code>tenant_{createForm.short_code || "…"}</code>
                {shortCodeManual ? " · manual override" : ""}. Locked after save.
              </span>
            </label>
            <label className="form-label">
              Status
              <select
                className="form-input"
                value={createForm.status}
                onChange={(e) =>
                  setCreateForm({ ...createForm, status: e.target.value as TenantStatus })
                }
              >
                {STATUS_OPTIONS.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </label>
            <label className="form-label">
              SLA level
              <select
                className="form-input"
                value={createForm.sla_level}
                onChange={(e) =>
                  setCreateForm({ ...createForm, sla_level: e.target.value as TenantSlaLevel })
                }
              >
                {SLA_OPTIONS.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </label>
            <label className="form-label">
              Business criticality
              <select
                className="form-input"
                value={createForm.business_criticality}
                onChange={(e) =>
                  setCreateForm({
                    ...createForm,
                    business_criticality: e.target.value as TenantCriticality,
                  })
                }
              >
                {CRITICALITY_OPTIONS.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </label>
            <label className="form-label">
              Timezone
              <select
                className="form-input"
                required
                value={
                  TIMEZONE_OPTIONS.includes(createForm.timezone)
                    ? createForm.timezone
                    : "Asia/Kolkata"
                }
                onChange={(e) => setCreateForm({ ...createForm, timezone: e.target.value })}
              >
                {TIMEZONE_OPTIONS.map((tz) => (
                  <option key={tz} value={tz}>
                    {tz.replace(/_/g, " ")}
                  </option>
                ))}
              </select>
            </label>
            <label className="form-label">
              Legal / registered name (optional)
              <input
                className="form-input"
                maxLength={200}
                placeholder="Registered company name if different"
                value={createForm.legal_name}
                onChange={(e) => setCreateForm({ ...createForm, legal_name: e.target.value })}
              />
            </label>
            <label className="form-label">
              Industry (optional)
              <select
                className="form-input"
                value={createForm.industry}
                onChange={(e) => setCreateForm({ ...createForm, industry: e.target.value })}
              >
                <option value="">Select industry…</option>
                {INDUSTRY_OPTIONS.map((i) => (
                  <option key={i} value={i}>
                    {i}
                  </option>
                ))}
              </select>
            </label>
            <label className="form-label">
              Company size (optional)
              <select
                className="form-input"
                value={createForm.company_size}
                onChange={(e) => setCreateForm({ ...createForm, company_size: e.target.value })}
              >
                <option value="">Select size…</option>
                {COMPANY_SIZE_OPTIONS.map((s) => (
                  <option key={s} value={s}>
                    {s} employees
                  </option>
                ))}
              </select>
            </label>
            <label className="form-label">
              Website (optional)
              <input
                className="form-input"
                maxLength={300}
                placeholder="https://example.com"
                value={createForm.website}
                onChange={(e) => setCreateForm({ ...createForm, website: e.target.value })}
              />
            </label>

            <p className="form-section-title" style={{ gridColumn: "1 / -1", margin: "0.5rem 0 0" }}>
              Primary contact
            </p>
            <label className="form-label">
              Contact name
              <input
                className="form-input"
                required
                maxLength={200}
                value={createForm.primary_contact_name}
                onChange={(e) =>
                  setCreateForm({ ...createForm, primary_contact_name: e.target.value })
                }
              />
            </label>
            <label className="form-label">
              Contact email
              <input
                className="form-input"
                required
                type="email"
                maxLength={320}
                value={createForm.primary_contact_email}
                onChange={(e) =>
                  setCreateForm({ ...createForm, primary_contact_email: e.target.value })
                }
              />
            </label>
            <label className="form-label">
              Contact phone (optional)
              <input
                className="form-input"
                maxLength={40}
                value={createForm.primary_contact_phone}
                onChange={(e) =>
                  setCreateForm({ ...createForm, primary_contact_phone: e.target.value })
                }
              />
            </label>
            <label className="form-label">
              Billing email (optional)
              <input
                className="form-input"
                type="email"
                maxLength={320}
                value={createForm.billing_email}
                onChange={(e) => setCreateForm({ ...createForm, billing_email: e.target.value })}
              />
            </label>

            <p className="form-section-title" style={{ gridColumn: "1 / -1", margin: "0.5rem 0 0" }}>
              Secondary contact (optional)
            </p>
            <label className="form-label">
              Secondary name
              <input
                className="form-input"
                maxLength={200}
                value={createForm.secondary_contact_name}
                onChange={(e) =>
                  setCreateForm({ ...createForm, secondary_contact_name: e.target.value })
                }
              />
            </label>
            <label className="form-label">
              Secondary email
              <input
                className="form-input"
                type="email"
                maxLength={320}
                value={createForm.secondary_contact_email}
                onChange={(e) =>
                  setCreateForm({ ...createForm, secondary_contact_email: e.target.value })
                }
              />
            </label>
            <label className="form-label">
              Secondary phone
              <input
                className="form-input"
                maxLength={40}
                value={createForm.secondary_contact_phone}
                onChange={(e) =>
                  setCreateForm({ ...createForm, secondary_contact_phone: e.target.value })
                }
              />
            </label>

            <p className="form-section-title" style={{ gridColumn: "1 / -1", margin: "0.5rem 0 0" }}>
              Address
            </p>
            <label className="form-label">
              Address line 1 (optional)
              <input
                className="form-input"
                maxLength={300}
                value={createForm.address_line1}
                onChange={(e) => setCreateForm({ ...createForm, address_line1: e.target.value })}
              />
            </label>
            <label className="form-label">
              Address line 2 (optional)
              <input
                className="form-input"
                maxLength={300}
                value={createForm.address_line2}
                onChange={(e) => setCreateForm({ ...createForm, address_line2: e.target.value })}
              />
            </label>
            <label className="form-label">
              City (optional)
              <input
                className="form-input"
                maxLength={120}
                value={createForm.city}
                onChange={(e) => setCreateForm({ ...createForm, city: e.target.value })}
              />
            </label>
            <label className="form-label">
              State / Region (optional)
              <input
                className="form-input"
                maxLength={120}
                value={createForm.state_region}
                onChange={(e) => setCreateForm({ ...createForm, state_region: e.target.value })}
              />
            </label>
            <label className="form-label">
              Postal code (optional)
              <input
                className="form-input"
                maxLength={32}
                value={createForm.postal_code}
                onChange={(e) => setCreateForm({ ...createForm, postal_code: e.target.value })}
              />
            </label>
            <label className="form-label">
              Country
              <select
                className="form-input"
                required
                value={createForm.country}
                onChange={(e) => setCreateForm({ ...createForm, country: e.target.value })}
              >
                <option value="">Select country…</option>
                {COUNTRY_OPTIONS.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </label>

            <p className="form-section-title" style={{ gridColumn: "1 / -1", margin: "0.5rem 0 0" }}>
              Contract &amp; commercial
            </p>
            <label className="form-label">
              Contract / MSA reference (optional)
              <input
                className="form-input"
                maxLength={120}
                placeholder="e.g. MSA-2026-014"
                value={createForm.contract_reference}
                onChange={(e) => setCreateForm({ ...createForm, contract_reference: e.target.value })}
              />
            </label>
            <label className="form-label">
              Tax / GST / VAT ID (optional)
              <input
                className="form-input"
                maxLength={64}
                value={createForm.tax_id}
                onChange={(e) => setCreateForm({ ...createForm, tax_id: e.target.value })}
              />
            </label>
            <label className="form-label">
              Contract start (optional)
              <input
                className="form-input"
                type="date"
                value={createForm.contract_start_date}
                onChange={(e) => setCreateForm({ ...createForm, contract_start_date: e.target.value })}
              />
            </label>
            <label className="form-label">
              Contract end (optional)
              <input
                className="form-input"
                type="date"
                value={createForm.contract_end_date}
                onChange={(e) => setCreateForm({ ...createForm, contract_end_date: e.target.value })}
              />
            </label>
            <label className="form-label">
              Licensed endpoints (optional)
              <input
                className="form-input"
                type="number"
                min={1}
                max={1000000}
                placeholder="e.g. 50"
                value={createForm.licensed_endpoints}
                onChange={(e) => setCreateForm({ ...createForm, licensed_endpoints: e.target.value })}
              />
            </label>
            <label className="form-label">
              Data residency (optional)
              <select
                className="form-input"
                value={createForm.data_residency}
                onChange={(e) => setCreateForm({ ...createForm, data_residency: e.target.value })}
              >
                <option value="">Select residency…</option>
                {DATA_RESIDENCY_OPTIONS.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
            </label>
            <label className="form-label">
              Preferred language
              <select
                className="form-input"
                value={createForm.preferred_language}
                onChange={(e) => setCreateForm({ ...createForm, preferred_language: e.target.value })}
              >
                {PREFERRED_LANGUAGE_OPTIONS.map((l) => (
                  <option key={l.value} value={l.value}>
                    {l.label}
                  </option>
                ))}
              </select>
            </label>

            <CreateEntitlementsFields
              value={createForm.entitlements}
              onChange={(entitlements) => setCreateForm({ ...createForm, entitlements })}
            />

            <p className="form-section-title" style={{ gridColumn: "1 / -1", margin: "0.5rem 0 0" }}>
              Customer portal admin (required)
            </p>
            <p className="page-subtitle form-grid-full" style={{ margin: 0 }}>
              Every customer gets a portal login at onboard. Leave email/name blank to use the
              primary contact. You set the initial password here (share it securely with the customer).
            </p>
            <label className="form-label">
              Portal admin email
              <input
                className="form-input"
                type="email"
                maxLength={320}
                placeholder="Defaults to primary contact email"
                value={createForm.portal_admin_email}
                onChange={(e) =>
                  setCreateForm({ ...createForm, portal_admin_email: e.target.value })
                }
              />
            </label>
            <label className="form-label">
              Portal admin full name
              <input
                className="form-input"
                maxLength={200}
                placeholder="Defaults to primary contact name"
                value={createForm.portal_admin_full_name}
                onChange={(e) =>
                  setCreateForm({ ...createForm, portal_admin_full_name: e.target.value })
                }
              />
            </label>
            <label className="form-label">
              Portal admin password
              <input
                className="form-input"
                type="password"
                required
                minLength={8}
                maxLength={128}
                autoComplete="new-password"
                value={createForm.portal_admin_password}
                onChange={(e) =>
                  setCreateForm({ ...createForm, portal_admin_password: e.target.value })
                }
              />
            </label>
            <label className="form-label">
              Portal admin phone (optional)
              <input
                className="form-input"
                maxLength={40}
                value={createForm.portal_admin_phone}
                onChange={(e) =>
                  setCreateForm({ ...createForm, portal_admin_phone: e.target.value })
                }
              />
            </label>

            <p className="form-section-title" style={{ gridColumn: "1 / -1", margin: "0.5rem 0 0" }}>
              Deployment
            </p>
            <label className="form-label">
              Deployment mode
              <select
                className="form-input"
                value={createForm.deployment_mode}
                onChange={(e) => {
                  const mode = e.target.value as TenantDeploymentMode;
                  setCreateForm({
                    ...createForm,
                    deployment_mode: mode,
                    cloud_provider: needsCloudProvider(mode)
                      ? createForm.cloud_provider || "aws"
                      : "",
                  });
                }}
              >
                {DEPLOYMENT_MODE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </label>
            {needsCloudProvider(createForm.deployment_mode) && (
              <label className="form-label">
                Cloud provider
                <select
                  className="form-input"
                  required={requiresCloudProviderStrict(createForm.deployment_mode)}
                  value={createForm.cloud_provider}
                  onChange={(e) =>
                    setCreateForm({
                      ...createForm,
                      cloud_provider: e.target.value as TenantCloudProvider | "",
                    })
                  }
                >
                  {createForm.deployment_mode === "hybrid" && (
                    <option value="">Not specified</option>
                  )}
                  {CLOUD_PROVIDER_OPTIONS.map((p) => (
                    <option key={p} value={p}>
                      {p.toUpperCase()}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <p className="page-subtitle form-grid-full" style={{ margin: 0 }}>
              {DEPLOYMENT_MODE_OPTIONS.find((o) => o.value === createForm.deployment_mode)?.hint}
            </p>
            <label className="form-label form-grid-full">
              Notes (internal)
              <textarea
                className="form-input"
                rows={3}
                value={createForm.notes}
                onChange={(e) => setCreateForm({ ...createForm, notes: e.target.value })}
              />
            </label>
          </div>
          {createError && <div className="form-error">{createError}</div>}
          <div className="confirm-actions">
            <button className="btn btn-primary" type="submit" disabled={creating}>
              {creating ? "Onboarding..." : "Onboard customer"}
            </button>
            <button
              className="btn btn-ghost"
              type="button"
              disabled={creating}
              onClick={() => setShowCreate(false)}
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      {editing && editForm && (
        <form
          ref={editPanelRef}
          className="management-panel"
          onSubmit={handleEdit}
          id="tenant-edit-panel"
        >
          <h2 className="section-title" style={{ marginTop: 0 }}>
            {canWrite ? "Edit" : "View"} {editing.name} ({editing.short_code})
          </h2>
          <p className="page-subtitle" style={{ marginBottom: "12px" }}>
            Short code cannot be changed after creation.
            {!canWrite ? " You can view details but not save changes." : ""}
          </p>
          <div className="form-grid" style={canWrite ? undefined : { pointerEvents: "none", opacity: 0.85 }}>
            <label className="form-label">
              Customer name
              <input
                className="form-input"
                required
                maxLength={200}
                value={editForm.name}
                onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                readOnly={!canWrite}
              />
            </label>
            <label className="form-label">
              Status
              <select
                className="form-input"
                value={editForm.status}
                onChange={(e) =>
                  setEditForm({ ...editForm, status: e.target.value as TenantStatus })
                }
              >
                {STATUS_OPTIONS.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </label>
            <label className="form-label">
              SLA level
              <select
                className="form-input"
                value={editForm.sla_level}
                onChange={(e) =>
                  setEditForm({ ...editForm, sla_level: e.target.value as TenantSlaLevel })
                }
              >
                {SLA_OPTIONS.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </label>
            <label className="form-label">
              Business criticality
              <select
                className="form-input"
                value={editForm.business_criticality}
                onChange={(e) =>
                  setEditForm({
                    ...editForm,
                    business_criticality: e.target.value as TenantCriticality,
                  })
                }
              >
                {CRITICALITY_OPTIONS.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </label>
            <label className="form-label">
              Timezone
              <select
                className="form-input"
                required
                value={
                  TIMEZONE_OPTIONS.includes(editForm.timezone)
                    ? editForm.timezone
                    : TIMEZONE_OPTIONS.includes("Asia/Kolkata")
                      ? "Asia/Kolkata"
                      : TIMEZONE_OPTIONS[0] || "UTC"
                }
                onChange={(e) => setEditForm({ ...editForm, timezone: e.target.value })}
              >
                {TIMEZONE_OPTIONS.map((tz) => (
                  <option key={tz} value={tz}>
                    {tz.replace(/_/g, " ")}
                  </option>
                ))}
              </select>
            </label>
            <label className="form-label">
              Legal / registered name (optional)
              <input
                className="form-input"
                maxLength={200}
                value={editForm.legal_name}
                onChange={(e) => setEditForm({ ...editForm, legal_name: e.target.value })}
              />
            </label>
            <label className="form-label">
              Industry (optional)
              <select
                className="form-input"
                value={editForm.industry}
                onChange={(e) => setEditForm({ ...editForm, industry: e.target.value })}
              >
                <option value="">Select industry…</option>
                {!INDUSTRY_OPTIONS.includes(editForm.industry) && editForm.industry ? (
                  <option value={editForm.industry}>{editForm.industry} (current)</option>
                ) : null}
                {INDUSTRY_OPTIONS.map((i) => (
                  <option key={i} value={i}>
                    {i}
                  </option>
                ))}
              </select>
            </label>
            <label className="form-label">
              Company size (optional)
              <select
                className="form-input"
                value={editForm.company_size}
                onChange={(e) => setEditForm({ ...editForm, company_size: e.target.value })}
              >
                <option value="">Select size…</option>
                {COMPANY_SIZE_OPTIONS.map((s) => (
                  <option key={s} value={s}>
                    {s} employees
                  </option>
                ))}
              </select>
            </label>
            <label className="form-label">
              Website (optional)
              <input
                className="form-input"
                maxLength={300}
                value={editForm.website}
                onChange={(e) => setEditForm({ ...editForm, website: e.target.value })}
              />
            </label>

            <p className="form-section-title" style={{ gridColumn: "1 / -1", margin: "0.5rem 0 0" }}>
              Primary contact
            </p>
            <label className="form-label">
              Contact name
              <input
                className="form-input"
                required
                maxLength={200}
                value={editForm.primary_contact_name}
                onChange={(e) =>
                  setEditForm({ ...editForm, primary_contact_name: e.target.value })
                }
              />
            </label>
            <label className="form-label">
              Contact email
              <input
                className="form-input"
                required
                type="email"
                maxLength={320}
                value={editForm.primary_contact_email}
                onChange={(e) =>
                  setEditForm({ ...editForm, primary_contact_email: e.target.value })
                }
              />
            </label>
            <label className="form-label">
              Contact phone (optional)
              <input
                className="form-input"
                maxLength={40}
                value={editForm.primary_contact_phone}
                onChange={(e) =>
                  setEditForm({ ...editForm, primary_contact_phone: e.target.value })
                }
              />
            </label>
            <label className="form-label">
              Billing email (optional)
              <input
                className="form-input"
                type="email"
                maxLength={320}
                value={editForm.billing_email}
                onChange={(e) => setEditForm({ ...editForm, billing_email: e.target.value })}
              />
            </label>

            <p className="form-section-title" style={{ gridColumn: "1 / -1", margin: "0.5rem 0 0" }}>
              Secondary contact (optional)
            </p>
            <label className="form-label">
              Secondary name
              <input
                className="form-input"
                maxLength={200}
                value={editForm.secondary_contact_name}
                onChange={(e) =>
                  setEditForm({ ...editForm, secondary_contact_name: e.target.value })
                }
              />
            </label>
            <label className="form-label">
              Secondary email
              <input
                className="form-input"
                type="email"
                maxLength={320}
                value={editForm.secondary_contact_email}
                onChange={(e) =>
                  setEditForm({ ...editForm, secondary_contact_email: e.target.value })
                }
              />
            </label>
            <label className="form-label">
              Secondary phone
              <input
                className="form-input"
                maxLength={40}
                value={editForm.secondary_contact_phone}
                onChange={(e) =>
                  setEditForm({ ...editForm, secondary_contact_phone: e.target.value })
                }
              />
            </label>

            <p className="form-section-title" style={{ gridColumn: "1 / -1", margin: "0.5rem 0 0" }}>
              Address
            </p>
            <label className="form-label">
              Address line 1 (optional)
              <input
                className="form-input"
                maxLength={300}
                value={editForm.address_line1}
                onChange={(e) => setEditForm({ ...editForm, address_line1: e.target.value })}
              />
            </label>
            <label className="form-label">
              Address line 2 (optional)
              <input
                className="form-input"
                maxLength={300}
                value={editForm.address_line2}
                onChange={(e) => setEditForm({ ...editForm, address_line2: e.target.value })}
              />
            </label>
            <label className="form-label">
              City (optional)
              <input
                className="form-input"
                maxLength={120}
                value={editForm.city}
                onChange={(e) => setEditForm({ ...editForm, city: e.target.value })}
              />
            </label>
            <label className="form-label">
              State / Region (optional)
              <input
                className="form-input"
                maxLength={120}
                value={editForm.state_region}
                onChange={(e) => setEditForm({ ...editForm, state_region: e.target.value })}
              />
            </label>
            <label className="form-label">
              Postal code (optional)
              <input
                className="form-input"
                maxLength={32}
                value={editForm.postal_code}
                onChange={(e) => setEditForm({ ...editForm, postal_code: e.target.value })}
              />
            </label>
            <label className="form-label">
              Country
              <select
                className="form-input"
                required
                value={editForm.country}
                onChange={(e) => setEditForm({ ...editForm, country: e.target.value })}
              >
                <option value="">Select country…</option>
                {!COUNTRY_OPTIONS.includes(editForm.country) && editForm.country ? (
                  <option value={editForm.country}>{editForm.country} (current)</option>
                ) : null}
                {COUNTRY_OPTIONS.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </label>

            <p className="form-section-title" style={{ gridColumn: "1 / -1", margin: "0.5rem 0 0" }}>
              Contract &amp; commercial
            </p>
            <label className="form-label">
              Contract / MSA reference (optional)
              <input
                className="form-input"
                maxLength={120}
                value={editForm.contract_reference}
                onChange={(e) => setEditForm({ ...editForm, contract_reference: e.target.value })}
              />
            </label>
            <label className="form-label">
              Tax / GST / VAT ID (optional)
              <input
                className="form-input"
                maxLength={64}
                value={editForm.tax_id}
                onChange={(e) => setEditForm({ ...editForm, tax_id: e.target.value })}
              />
            </label>
            <label className="form-label">
              Contract start (optional)
              <input
                className="form-input"
                type="date"
                value={editForm.contract_start_date}
                onChange={(e) => setEditForm({ ...editForm, contract_start_date: e.target.value })}
              />
            </label>
            <label className="form-label">
              Contract end (optional)
              <input
                className="form-input"
                type="date"
                value={editForm.contract_end_date}
                onChange={(e) => setEditForm({ ...editForm, contract_end_date: e.target.value })}
              />
            </label>
            <label className="form-label">
              Licensed endpoints (optional)
              <input
                className="form-input"
                type="number"
                min={1}
                max={1000000}
                value={editForm.licensed_endpoints}
                onChange={(e) => setEditForm({ ...editForm, licensed_endpoints: e.target.value })}
              />
            </label>
            <label className="form-label">
              Data residency (optional)
              <select
                className="form-input"
                value={editForm.data_residency}
                onChange={(e) => setEditForm({ ...editForm, data_residency: e.target.value })}
              >
                <option value="">Select residency…</option>
                {!DATA_RESIDENCY_OPTIONS.includes(editForm.data_residency) && editForm.data_residency ? (
                  <option value={editForm.data_residency}>{editForm.data_residency} (current)</option>
                ) : null}
                {DATA_RESIDENCY_OPTIONS.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
            </label>
            <label className="form-label">
              Preferred language
              <select
                className="form-input"
                value={editForm.preferred_language}
                onChange={(e) => setEditForm({ ...editForm, preferred_language: e.target.value })}
              >
                {PREFERRED_LANGUAGE_OPTIONS.map((l) => (
                  <option key={l.value} value={l.value}>
                    {l.label}
                  </option>
                ))}
              </select>
            </label>

            <p className="form-section-title" style={{ gridColumn: "1 / -1", margin: "0.5rem 0 0" }}>
              Deployment
            </p>
            <label className="form-label">
              Deployment mode
              <select
                className="form-input"
                value={editForm.deployment_mode}
                onChange={(e) => {
                  const mode = e.target.value as TenantDeploymentMode;
                  setEditForm({
                    ...editForm,
                    deployment_mode: mode,
                    cloud_provider: needsCloudProvider(mode)
                      ? editForm.cloud_provider || "aws"
                      : "",
                  });
                }}
              >
                {DEPLOYMENT_MODE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </label>
            {needsCloudProvider(editForm.deployment_mode) && (
              <label className="form-label">
                Cloud provider
                <select
                  className="form-input"
                  required={requiresCloudProviderStrict(editForm.deployment_mode)}
                  value={editForm.cloud_provider}
                  onChange={(e) =>
                    setEditForm({
                      ...editForm,
                      cloud_provider: e.target.value as TenantCloudProvider | "",
                    })
                  }
                >
                  {editForm.deployment_mode === "hybrid" && (
                    <option value="">Not specified</option>
                  )}
                  {CLOUD_PROVIDER_OPTIONS.map((p) => (
                    <option key={p} value={p}>
                      {p.toUpperCase()}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <p className="page-subtitle form-grid-full" style={{ margin: 0 }}>
              {DEPLOYMENT_MODE_OPTIONS.find((o) => o.value === editForm.deployment_mode)?.hint}
            </p>
            <label className="form-label form-grid-full">
              Notes (optional — leave blank to clear, or type new notes)
              <textarea
                className="form-input"
                rows={3}
                value={editForm.notes}
                onChange={(e) => setEditForm({ ...editForm, notes: e.target.value })}
              />
            </label>
          </div>
          {editError && <div className="form-error">{editError}</div>}
          <div className="confirm-actions">
            {canWrite && (
              <button className="btn btn-primary" type="submit" disabled={saving}>
                {saving ? "Saving..." : "Save changes"}
              </button>
            )}
            <button
              className="btn btn-ghost"
              type="button"
              disabled={saving}
              onClick={() => {
                setEditing(null);
                setEditForm(null);
              }}
            >
              {canWrite ? "Cancel" : "Close"}
            </button>
          </div>
        </form>
      )}

      {status === "loading" && <div className="state-message">Loading customers...</div>}
      {status === "forbidden" && (
        <div className="state-message state-error">
          Access denied. Your account does not have permission to view customers.
        </div>
      )}
      {status === "error" && <div className="state-message state-error">{errorMessage}</div>}

      {status === "success" && data && (
        data.tenants.length === 0 ? (
          <div className="state-message">No customers yet. Use Add Customer to onboard the first one.</div>
        ) : (
          <>
            <div className="command-chip-row" role="toolbar" aria-label="Filter by deployment mode">
              <button
                type="button"
                className={"command-chip" + (modeFilter === "all" ? " is-active" : "")}
                onClick={() => setModeFilter("all")}
              >
                All ({data.tenants.length})
              </button>
              {DEPLOYMENT_MODE_OPTIONS.map((o) => {
                const count = data.tenants.filter((t) => t.deployment_mode === o.value).length;
                return (
                  <button
                    key={o.value}
                    type="button"
                    className={"command-chip" + (modeFilter === o.value ? " is-active" : "")}
                    onClick={() => setModeFilter(o.value)}
                  >
                    {o.label.split(" (")[0]} ({count})
                  </button>
                );
              })}
            </div>
            {filteredTenants.length === 0 ? (
              <div className="state-message">No customers match this deployment filter.</div>
            ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Short Code</th>
                <th>Deployment</th>
                <th>Country</th>
                <th>Primary contact</th>
                <th>Status</th>
                <th>SLA Level</th>
                <th>Criticality</th>
                <th>Appliances</th>
                <th>Protected Assets</th>
                <th>Incidents</th>
                {canWrite && <th>Actions</th>}
              </tr>
            </thead>
            <tbody>
              {filteredTenants.map((tenant) => (
                <tr key={tenant.id}>
                  <td>
                    <button
                      type="button"
                      className="linkish"
                      onClick={() => openEdit(tenant)}
                      title="Open customer details"
                    >
                      {tenant.name}
                    </button>
                  </td>
                  <td>{tenant.short_code}</td>
                  <td>
                    <span className={`badge badge-mode badge-mode-${tenant.deployment_mode || "cloud"}`}>
                      {deploymentModeLabel(tenant.deployment_mode)}
                      {tenant.cloud_provider ? ` · ${tenant.cloud_provider.toUpperCase()}` : ""}
                    </span>
                  </td>
                  <td>{tenant.country || "—"}</td>
                  <td>
                    {tenant.primary_contact_name || tenant.primary_contact_email ? (
                      <>
                        <div>{tenant.primary_contact_name || "—"}</div>
                        <div className="muted-text">{tenant.primary_contact_email || ""}</div>
                      </>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td>
                    <span className={`badge badge-${tenant.status}`}>{tenant.status}</span>
                  </td>
                  <td>{tenant.sla_level}</td>
                  <td>{tenant.business_criticality}</td>
                  <td>{tenant.appliances}</td>
                  <td>{tenant.protected_assets}</td>
                  <td>{tenant.incidents}</td>
                  {canWrite && (
                    <td>
                      <RowActionsMenu
                        actions={[
                          {
                            id: "edit",
                            label: "Edit Details",
                            onClick: () => openEdit(tenant),
                          },
                          {
                            id: "subscription",
                            label: "Change Subscription",
                            onClick: () => setSubscriptionTenant(tenant),
                          },
                          {
                            id: "engines",
                            label: "Engine binding / provision",
                            onClick: () => void showEngineBinding(tenant),
                            disabled: engineBusy,
                          },
                          {
                            id: "suspend",
                            label: "Suspend Tenant",
                            onClick: () => void suspendTenant(tenant),
                            disabled: tenant.status === "suspended" || actionBusy,
                          },
                          {
                            id: "delete",
                            label: "Delete / Offboard",
                            danger: true,
                            onClick: () => setOffboardTenant(tenant),
                            disabled: actionBusy,
                          },
                        ]}
                      />
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
            )}
          </>
        )
      )}
    </div>
  );
}

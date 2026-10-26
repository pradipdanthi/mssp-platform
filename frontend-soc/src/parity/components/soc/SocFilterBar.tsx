import { FormEvent, useEffect, useMemo, useState } from "react";
import type { ListPaginationMeta } from "../ListToolbar";
import RuleIdCombobox, { type RuleFacetOption } from "./RuleIdCombobox";
import {
  deleteSocPreset,
  loadSocPresets,
  type SocSavedPreset,
  upsertSocPreset,
} from "./savedPresets";

export type SocFilterValues = {
  q: string;
  status: string;
  severity: string;
  /** URL `category` → API `asset_category` (KB-082 device taxonomy). */
  category: string;
  rule_id: string;
  hostname: string;
  process: string;
  path: string;
  user: string;
  hash: string;
  cmdline: string;
  since: string;
};

export type SocFilterBarProps = {
  searchPlaceholder?: string;
  values: SocFilterValues;
  onChange: (patch: Partial<SocFilterValues> & { page?: string }) => void;
  statusOptions: { value: string; label: string }[];
  severityOptions: { value: string; label: string }[];
  /** When false, hides alert forensic facets (e.g. incidents). */
  showAlertFacets?: boolean;
  /** Compact device-type dropdown (replaces left-rail taxonomy). */
  showDeviceTypeFilter?: boolean;
  /** Optional hit counts from taxonomy-summary (`Windows Systems (587)`). */
  deviceTypeCounts?: Record<string, number>;
  /** localStorage namespace for saved views, e.g. admin.alerts */
  presetNamespace?: string;
  /** Optional searchable Rule ID facets loader. */
  loadRuleFacets?: (q: string) => Promise<RuleFacetOption[]>;
  pageSize: number;
  onPageSizeChange: (size: number) => void;
  meta?: ListPaginationMeta | null;
  onPageChange: (page: number) => void;
};

const PAGE_SIZES = [25, 50, 100];
const TIME_PRESETS = [
  { value: "", label: "Any time" },
  { value: "15m", label: "Last 15m" },
  { value: "1h", label: "Last 1h" },
  { value: "24h", label: "Last 24h" },
  { value: "7d", label: "Last 7d" },
];

export const EMPTY_SOC_FILTERS: SocFilterValues = {
  q: "",
  status: "",
  severity: "",
  category: "",
  rule_id: "",
  hostname: "",
  process: "",
  path: "",
  user: "",
  hash: "",
  cmdline: "",
  since: "",
};

const DEVICE_TYPE_GROUPS: { label: string; options: { value: string; label: string }[] }[] = [
  {
    label: "Endpoints & workloads",
    options: [
      { value: "endpoints_windows", label: "Windows Systems" },
      { value: "endpoints_linux", label: "Linux & Unix" },
      { value: "endpoints_vm_container", label: "VMs & Containers" },
    ],
  },
  {
    label: "Network & connectivity",
    options: [
      { value: "network_ids_sensors", label: "Network IDS / Sensors" },
      { value: "network_hardware", label: "Network Hardware" },
    ],
  },
  {
    label: "Security, data & identity",
    options: [
      { value: "security_edge_appliances", label: "Firewalls / WAF / VPN" },
      { value: "databases_storage", label: "Databases & Storage" },
      { value: "identity_access", label: "Identity & Access" },
      { value: "iot_ot", label: "IoT / OT / Peripherals" },
    ],
  },
  {
    label: "Vulnerabilities & posture",
    options: [
      { value: "vuln_web_app", label: "Web / API (Aegis)" },
      { value: "vuln_infrastructure", label: "Infrastructure CVE" },
    ],
  },
];

function withCount(label: string, slug: string, counts?: Record<string, number>): string {
  if (!counts || counts[slug] == null) return label;
  return `${label} (${counts[slug]})`;
}

function deviceTypeChipLabel(category: string, counts?: Record<string, number>): string {
  if (category === "uncategorized") return withCount("Uncategorized", "uncategorized", counts);
  for (const group of DEVICE_TYPE_GROUPS) {
    const opt = group.options.find((o) => o.value === category);
    if (opt) return withCount(opt.label, opt.value, counts);
  }
  return category.replace(/_/g, " ");
}

function facetKeys(
  showAlertFacets: boolean,
  showDeviceTypeFilter: boolean
): (keyof SocFilterValues)[] {
  const base: (keyof SocFilterValues)[] = ["q", "status", "severity", "since"];
  if (showDeviceTypeFilter) base.push("category");
  if (showAlertFacets) {
    return [...base, "rule_id", "hostname", "process", "path", "user", "hash", "cmdline"];
  }
  return base;
}

export default function SocFilterBar({
  searchPlaceholder = "Search title, rule, host, process, path, user…",
  values,
  onChange,
  statusOptions,
  severityOptions,
  showAlertFacets = true,
  showDeviceTypeFilter = false,
  deviceTypeCounts,
  presetNamespace,
  loadRuleFacets,
  pageSize,
  onPageSizeChange,
  meta,
  onPageChange,
}: SocFilterBarProps) {
  const [draft, setDraft] = useState(values.q);
  const [facetDraft, setFacetDraft] = useState({
    rule_id: values.rule_id,
    hostname: values.hostname,
    process: values.process,
    path: values.path,
    user: values.user,
    hash: values.hash,
    cmdline: values.cmdline,
  });
  const [presets, setPresets] = useState<SocSavedPreset[]>([]);
  const [presetName, setPresetName] = useState("");
  const [showMore, setShowMore] = useState(false);

  useEffect(() => {
    setDraft(values.q);
  }, [values.q]);

  useEffect(() => {
    setFacetDraft({
      rule_id: values.rule_id,
      hostname: values.hostname,
      process: values.process,
      path: values.path,
      user: values.user,
      hash: values.hash,
      cmdline: values.cmdline,
    });
    const hasExtra =
      Boolean(values.user) ||
      Boolean(values.hash) ||
      Boolean(values.cmdline) ||
      Boolean(values.path);
    if (hasExtra) setShowMore(true);
  }, [
    values.rule_id,
    values.hostname,
    values.process,
    values.path,
    values.user,
    values.hash,
    values.cmdline,
  ]);

  useEffect(() => {
    if (presetNamespace) setPresets(loadSocPresets(presetNamespace));
  }, [presetNamespace]);

  function submitSearch(e: FormEvent) {
    e.preventDefault();
    onChange({
      q: draft.trim(),
      ...(showAlertFacets
        ? {
            rule_id: facetDraft.rule_id.trim(),
            hostname: facetDraft.hostname.trim(),
            process: facetDraft.process.trim(),
            path: facetDraft.path.trim(),
            user: facetDraft.user.trim(),
            hash: facetDraft.hash.trim(),
            cmdline: facetDraft.cmdline.trim(),
          }
        : {}),
      page: "1",
    });
  }

  function clearAll() {
    setDraft("");
    setFacetDraft({
      rule_id: "",
      hostname: "",
      process: "",
      path: "",
      user: "",
      hash: "",
      cmdline: "",
    });
    onChange({ ...EMPTY_SOC_FILTERS, page: "1" });
  }

  function applyPreset(preset: SocSavedPreset) {
    const next: SocFilterValues = { ...EMPTY_SOC_FILTERS };
    for (const key of facetKeys(showAlertFacets, showDeviceTypeFilter)) {
      if (preset.filters[key]) next[key] = preset.filters[key];
    }
    setDraft(next.q);
    setFacetDraft({
      rule_id: next.rule_id,
      hostname: next.hostname,
      process: next.process,
      path: next.path,
      user: next.user,
      hash: next.hash,
      cmdline: next.cmdline,
    });
    onChange({ ...next, page: "1" });
  }

  function saveCurrentPreset() {
    if (!presetNamespace || !presetName.trim()) return;
    const filters: Record<string, string> = {};
    for (const key of facetKeys(showAlertFacets, showDeviceTypeFilter)) {
      const v = values[key];
      if (v) filters[key] = v;
    }
    setPresets(upsertSocPreset(presetNamespace, presetName, filters));
    setPresetName("");
  }

  const chips = useMemo(() => {
    const out: { key: keyof SocFilterValues; label: string }[] = [];
    if (values.q) out.push({ key: "q", label: `Search: ${values.q}` });
    if (values.status) {
      const opt = statusOptions.find((o) => o.value === values.status);
      out.push({ key: "status", label: `Status: ${opt?.label ?? values.status}` });
    }
    if (values.severity) {
      const opt = severityOptions.find((o) => o.value === values.severity);
      out.push({ key: "severity", label: `Severity: ${opt?.label ?? values.severity}` });
    }
    if (values.since) {
      const opt = TIME_PRESETS.find((o) => o.value === values.since);
      out.push({ key: "since", label: `Time: ${opt?.label ?? values.since}` });
    }
    if (showDeviceTypeFilter && values.category) {
      out.push({
        key: "category",
        label: `Device: ${deviceTypeChipLabel(values.category, deviceTypeCounts)}`,
      });
    }
    if (values.rule_id) out.push({ key: "rule_id", label: `Rule: ${values.rule_id}` });
    if (values.hostname) out.push({ key: "hostname", label: `Host: ${values.hostname}` });
    if (values.process) out.push({ key: "process", label: `Process: ${values.process}` });
    if (values.path) out.push({ key: "path", label: `Path: ${values.path}` });
    if (values.user) out.push({ key: "user", label: `User: ${values.user}` });
    if (values.hash) out.push({ key: "hash", label: `Hash: ${values.hash.slice(0, 16)}…` });
    if (values.cmdline) out.push({ key: "cmdline", label: `Cmd: ${values.cmdline}` });
    return out;
  }, [values, statusOptions, severityOptions, showDeviceTypeFilter, deviceTypeCounts]);

  const hasActive = chips.length > 0;
  const total = meta?.total ?? 0;
  const page = meta?.page ?? 1;
  const totalPages = meta?.total_pages ?? 0;
  const from = total === 0 ? 0 : (page - 1) * (meta?.page_size ?? pageSize) + 1;
  const to = Math.min(page * (meta?.page_size ?? pageSize), total);

  return (
    <div className="list-toolbar soc-filter-bar" data-testid="soc-filter-bar">
      {presetNamespace ? (
        <div className="soc-preset-row" data-testid="soc-presets">
          <span className="soc-preset-label">Saved views</span>
          {presets.length === 0 ? (
            <span className="muted soc-preset-empty">None yet — set filters, name, Save</span>
          ) : (
            presets.map((p) => (
              <span key={p.id} className="soc-preset-chip">
                <button type="button" className="btn btn-ghost btn-small" onClick={() => applyPreset(p)}>
                  {p.name}
                </button>
                <button
                  type="button"
                  className="soc-preset-remove"
                  aria-label={`Delete preset ${p.name}`}
                  onClick={() => setPresets(deleteSocPreset(presetNamespace, p.id))}
                >
                  ×
                </button>
              </span>
            ))
          )}
          <input
            className="list-toolbar-input list-toolbar-input--narrow"
            placeholder="Name this view…"
            value={presetName}
            onChange={(e) => setPresetName(e.target.value)}
            maxLength={80}
          />
          <button
            type="button"
            className="btn btn-ghost btn-small"
            disabled={!presetName.trim() || !hasActive}
            onClick={saveCurrentPreset}
          >
            Save view
          </button>
        </div>
      ) : null}

      <form className="list-toolbar-filters" onSubmit={submitSearch}>
        <label className="list-toolbar-field list-toolbar-field--grow">
          <span className="visually-hidden">Search</span>
          <input
            type="search"
            className="list-toolbar-input"
            data-testid="list-search"
            placeholder={searchPlaceholder}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
          />
        </label>
        <button type="submit" className="btn btn-ghost btn-small" data-testid="list-search-submit">
          Search
        </button>
        <label className="list-toolbar-field">
          <span>Status</span>
          <select
            data-testid="list-status-filter"
            value={values.status}
            onChange={(e) => onChange({ status: e.target.value, page: "1" })}
          >
            <option value="">All</option>
            {statusOptions.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <label className="list-toolbar-field">
          <span>Severity</span>
          <select
            data-testid="list-severity-filter"
            value={values.severity}
            onChange={(e) => onChange({ severity: e.target.value, page: "1" })}
          >
            <option value="">All</option>
            {severityOptions.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <label className="list-toolbar-field">
          <span>Time</span>
          <select
            data-testid="list-since-filter"
            value={values.since}
            onChange={(e) => onChange({ since: e.target.value, page: "1" })}
          >
            {TIME_PRESETS.map((o) => (
              <option key={o.value || "any"} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        {showDeviceTypeFilter ? (
          <label className="list-toolbar-field">
            <span>Device type</span>
            <select
              data-testid="list-device-type-filter"
              value={values.category}
              onChange={(e) => onChange({ category: e.target.value, page: "1" })}
            >
              <option value="">{withCount("All Devices", "all", deviceTypeCounts)}</option>
              <option value="uncategorized">
                {withCount("Uncategorized", "uncategorized", deviceTypeCounts)}
              </option>
              {DEVICE_TYPE_GROUPS.map((group) => (
                <optgroup key={group.label} label={group.label}>
                  {group.options.map((o) => (
                    <option key={o.value} value={o.value}>
                      {withCount(o.label, o.value, deviceTypeCounts)}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </label>
        ) : null}
        {showAlertFacets ? (
          <>
            <label className="list-toolbar-field">
              <span>Rule ID</span>
              <RuleIdCombobox
                value={facetDraft.rule_id}
                loadFacets={loadRuleFacets}
                onDraftChange={(rule_id) => setFacetDraft((d) => ({ ...d, rule_id }))}
                onSelect={(rule_id) => {
                  setFacetDraft((d) => ({ ...d, rule_id }));
                  onChange({ rule_id, page: "1" });
                }}
              />
            </label>
            <label className="list-toolbar-field">
              <span>Hostname</span>
              <input
                className="list-toolbar-input list-toolbar-input--narrow"
                data-testid="filter-hostname"
                value={facetDraft.hostname}
                onChange={(e) => setFacetDraft((d) => ({ ...d, hostname: e.target.value }))}
                placeholder="Host / agent"
              />
            </label>
            <label className="list-toolbar-field">
              <span>Process</span>
              <input
                className="list-toolbar-input list-toolbar-input--narrow"
                data-testid="filter-process"
                value={facetDraft.process}
                onChange={(e) => setFacetDraft((d) => ({ ...d, process: e.target.value }))}
                placeholder="Image / name"
              />
            </label>
            <button
              type="button"
              className="btn btn-ghost btn-small"
              onClick={() => setShowMore((v) => !v)}
            >
              {showMore ? "Less" : "More filters"}
            </button>
            {showMore ? (
              <>
                <label className="list-toolbar-field">
                  <span>Path</span>
                  <input
                    className="list-toolbar-input list-toolbar-input--narrow"
                    data-testid="filter-path"
                    value={facetDraft.path}
                    onChange={(e) => setFacetDraft((d) => ({ ...d, path: e.target.value }))}
                    placeholder="*\\Temp\\* "
                  />
                </label>
                <label className="list-toolbar-field">
                  <span>User</span>
                  <input
                    className="list-toolbar-input list-toolbar-input--narrow"
                    data-testid="filter-user"
                    value={facetDraft.user}
                    onChange={(e) => setFacetDraft((d) => ({ ...d, user: e.target.value }))}
                    placeholder="Account"
                  />
                </label>
                <label className="list-toolbar-field">
                  <span>Hash</span>
                  <input
                    className="list-toolbar-input list-toolbar-input--narrow"
                    data-testid="filter-hash"
                    value={facetDraft.hash}
                    onChange={(e) => setFacetDraft((d) => ({ ...d, hash: e.target.value }))}
                    placeholder="SHA256 / MD5"
                  />
                </label>
                <label className="list-toolbar-field">
                  <span>Cmdline</span>
                  <input
                    className="list-toolbar-input list-toolbar-input--narrow"
                    data-testid="filter-cmdline"
                    value={facetDraft.cmdline}
                    onChange={(e) => setFacetDraft((d) => ({ ...d, cmdline: e.target.value }))}
                    placeholder="-encodedcommand"
                  />
                </label>
              </>
            ) : null}
          </>
        ) : null}
        <label className="list-toolbar-field">
          <span>Per page</span>
          <select value={pageSize} onChange={(e) => onPageSizeChange(Number(e.target.value))}>
            {PAGE_SIZES.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        {hasActive ? (
          <button type="button" className="btn btn-ghost btn-small" onClick={clearAll}>
            Clear filters
          </button>
        ) : null}
      </form>

      {chips.length > 0 ? (
        <div className="soc-filter-chips" data-testid="soc-filter-chips">
          {chips.map((c) => (
            <button
              key={c.key}
              type="button"
              className="soc-filter-chip"
              onClick={() => onChange({ [c.key]: "", page: "1" })}
              title="Remove filter"
            >
              {c.label} ×
            </button>
          ))}
        </div>
      ) : null}

      <div className="list-toolbar-pager">
        <span className="list-toolbar-range">
          {total === 0 ? "0 results" : `${from}–${to} of ${total}`}
        </span>
        <button
          type="button"
          className="btn btn-ghost btn-small"
          disabled={!meta?.has_prev}
          onClick={() => onPageChange(page - 1)}
        >
          Previous
        </button>
        <span className="list-toolbar-page">
          Page {totalPages === 0 ? 0 : page} / {totalPages}
        </span>
        <button
          type="button"
          className="btn btn-ghost btn-small"
          disabled={!meta?.has_next}
          onClick={() => onPageChange(page + 1)}
        >
          Next
        </button>
      </div>
    </div>
  );
}

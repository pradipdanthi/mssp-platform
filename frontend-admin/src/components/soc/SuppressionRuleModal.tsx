import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  AlertDetail,
  createSuppression,
  getAlertDetail,
  SuppressionCreateRequest,
  SuppressionScope,
} from "../../api/admin";
import { ApiError } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";

export type SuppressionSeedAlert = {
  id: string;
  tenant_name?: string;
  short_code?: string;
  wazuh_rule_id?: string | null;
  process_name?: string | null;
  parent_process_name?: string | null;
  hash_sha256?: string | null;
  hash_md5?: string | null;
  file_path?: string | null;
  asset_hostname?: string | null;
  destination_host?: string | null;
  contextual?: Record<string, unknown>;
};

type ExpirationPreset = "permanent" | "7d" | "30d" | "90d";

type Props = {
  open: boolean;
  seedAlerts: SuppressionSeedAlert[];
  onClose: () => void;
  /** Called after a suppression is created successfully. */
  onCreated: (suppressionId: string) => void | Promise<void>;
  /** Optional AI Tier-1 suggested suppress scope (pre-fills rule/path/reason). */
  aiPrefill?: {
    rule_id?: string | null;
    process_path?: string | null;
    justification?: string | null;
  } | null;
};

function expiresAtFromPreset(preset: ExpirationPreset): string | null {
  if (preset === "permanent") return null;
  const days = preset === "7d" ? 7 : preset === "30d" ? 30 : 90;
  const d = new Date();
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString();
}

function pickCommon(values: Array<string | null | undefined>): string {
  const cleaned = values.map((v) => (v || "").trim()).filter(Boolean);
  if (cleaned.length === 0) return "";
  const first = cleaned[0];
  return cleaned.every((v) => v === first) ? first : first;
}

function hostnameFromSeed(a: SuppressionSeedAlert): string {
  return (
    a.asset_hostname ||
    a.destination_host ||
    (typeof a.contextual?.hostname === "string" ? a.contextual.hostname : "") ||
    ""
  );
}

export default function SuppressionRuleModal({ open, seedAlerts, onClose, onCreated, aiPrefill }: Props) {
  const { user } = useAuth();
  const canGlobal = user?.role === "platform_admin" || user?.role === "soc_manager";

  const [loadingSeed, setLoadingSeed] = useState(false);
  const [detail, setDetail] = useState<AlertDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [scope, setScope] = useState<SuppressionScope>(canGlobal ? "global" : "tenant");
  const [ruleId, setRuleId] = useState("");
  const [tenantId, setTenantId] = useState<string | null>(null);
  const [hostname, setHostname] = useState("");
  const [matchProcessPath, setMatchProcessPath] = useState(false);
  const [processPathValue, setProcessPathValue] = useState("");
  const [matchParentProcess, setMatchParentProcess] = useState(false);
  const [parentProcessValue, setParentProcessValue] = useState("");
  const [matchFileHash, setMatchFileHash] = useState(false);
  const [fileHashValue, setFileHashValue] = useState("");
  const [matchHostname, setMatchHostname] = useState(false);
  const [hostnameValue, setHostnameValue] = useState("");
  const [expiration, setExpiration] = useState<ExpirationPreset>("30d");
  const [reason, setReason] = useState("");

  const primaryId = seedAlerts[0]?.id;

  useEffect(() => {
    if (!open || !primaryId) return;
    let cancelled = false;
    setLoadingSeed(true);
    setError(null);
    getAlertDetail(primaryId)
      .then((res) => {
        if (cancelled) return;
        const alert = res.alert;
        setDetail(alert);
        const seeds = seedAlerts;
        const rule = pickCommon([
          aiPrefill?.rule_id,
          alert.wazuh_rule_id,
          ...seeds.map((s) => s.wazuh_rule_id),
        ]);
        const proc = pickCommon([
          aiPrefill?.process_path,
          alert.file_path || alert.process_name,
          ...seeds.map((s) => s.file_path || s.process_name),
        ]);
        const parent = pickCommon([
          alert.parent_process_name,
          ...seeds.map((s) => s.parent_process_name),
        ]);
        const hash = pickCommon([
          alert.hash_sha256 || alert.hash_md5,
          ...seeds.map((s) => s.hash_sha256 || s.hash_md5),
        ]);
        const host = pickCommon([
          alert.asset_hostname || alert.destination_host,
          ...seeds.map(hostnameFromSeed),
        ]);

        setRuleId(rule);
        setTenantId(alert.tenant_id);
        setHostname(host);
        setProcessPathValue(proc);
        setParentProcessValue(parent);
        setFileHashValue(hash);
        setHostnameValue(host);
        setMatchProcessPath(Boolean(proc));
        setMatchParentProcess(Boolean(parent));
        setMatchFileHash(Boolean(hash));
        setMatchHostname(Boolean(host) && !canGlobal);
        setScope(canGlobal ? "global" : host ? "host" : "tenant");
        setExpiration("30d");
        setReason(
          (aiPrefill?.justification || "").trim() ||
            (seeds.length > 1
              ? `Bulk suppress ${seeds.length} alerts (rule ${rule || "n/a"})`
              : `Suppress from alert ${alert.alert_title}`)
        );
      })
      .catch((err) => {
        if (cancelled) return;
        setError(
          err instanceof ApiError && typeof err.detail === "string"
            ? err.detail
            : "Unable to load alert evidence for suppression."
        );
      })
      .finally(() => {
        if (!cancelled) setLoadingSeed(false);
      });

    return () => {
      cancelled = true;
    };
    // Only re-seed when modal opens for a new primary selection / AI prefill.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, primaryId, aiPrefill?.rule_id, aiPrefill?.process_path, aiPrefill?.justification]);

  const scopeHint = useMemo(() => {
    if (scope === "global") return "Applies to all tenants (platform_admin / soc_manager only).";
    if (scope === "tenant") return `Applies to ${detail?.tenant_name || "this tenant"} only.`;
    return `Applies to host “${hostname || hostnameValue || "…"}” within the tenant.`;
  }, [scope, detail?.tenant_name, hostname, hostnameValue]);

  if (!open) return null;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      if (!ruleId.trim()) {
        setError("Rule ID is required.");
        setBusy(false);
        return;
      }
      if (scope !== "global" && !tenantId) {
        setError("Tenant is required for tenant/host scope.");
        setBusy(false);
        return;
      }
      if (scope === "host" && !(hostname || hostnameValue).trim()) {
        setError("Hostname is required for host scope.");
        setBusy(false);
        return;
      }

      const payload: SuppressionCreateRequest = {
        scope,
        rule_id: ruleId.trim(),
        tenant_id: scope === "global" ? null : tenantId,
        hostname: scope === "host" ? (hostname || hostnameValue).trim() : null,
        match_process_path: matchProcessPath,
        process_path_value: matchProcessPath ? processPathValue.trim() || null : null,
        match_parent_process: matchParentProcess,
        parent_process_value: matchParentProcess ? parentProcessValue.trim() || null : null,
        match_file_hash: matchFileHash,
        file_hash_value: matchFileHash ? fileHashValue.trim() || null : null,
        match_hostname: matchHostname,
        hostname_value: matchHostname ? (hostnameValue || hostname).trim() || null : null,
        expires_at: expiresAtFromPreset(expiration),
        reason: reason.trim() || null,
      };

      const res = await createSuppression(payload);
      await onCreated(res.suppression.id);
      onClose();
    } catch (err) {
      setError(
        err instanceof ApiError && typeof err.detail === "string"
          ? err.detail
          : "Unable to create suppression."
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-root" role="dialog" aria-modal="true" aria-label="Create suppression">
      <button type="button" className="modal-backdrop" aria-label="Cancel" onClick={onClose} />
      <form className="modal-card card-surface modal-card--wide" onSubmit={submit}>
        <h2 className="modal-title">Suppress matching alerts</h2>
        <p className="modal-body">
          Future alerts matching this rule and selected criteria will be muted as false positives
          (customer-hidden) before incident creation.
        </p>

        {loadingSeed ? <p className="modal-hint">Loading evidence…</p> : null}
        {error ? <div className="state-message state-error">{error}</div> : null}

        <div className="soc-suppress-grid">
          <label className="list-toolbar-field">
            <span>Scope</span>
            <select
              value={scope}
              onChange={(e) => setScope(e.target.value as SuppressionScope)}
              disabled={busy}
            >
              {canGlobal ? <option value="global">Global</option> : null}
              <option value="tenant">Tenant</option>
              <option value="host">Host</option>
            </select>
          </label>
          <label className="list-toolbar-field">
            <span>Rule ID</span>
            <input
              className="form-input"
              value={ruleId}
              onChange={(e) => setRuleId(e.target.value)}
              required
              disabled={busy}
            />
          </label>
          <label className="list-toolbar-field">
            <span>Expires</span>
            <select
              value={expiration}
              onChange={(e) => setExpiration(e.target.value as ExpirationPreset)}
              disabled={busy}
            >
              <option value="permanent">Permanent</option>
              <option value="7d">7 days</option>
              <option value="30d">30 days</option>
              <option value="90d">90 days</option>
            </select>
          </label>
        </div>
        <p className="modal-hint">{scopeHint}</p>

        {(scope === "host" || matchHostname) && (
          <label className="list-toolbar-field" style={{ marginBottom: 12 }}>
            <span>Hostname</span>
            <input
              className="form-input"
              value={hostname}
              onChange={(e) => {
                setHostname(e.target.value);
                setHostnameValue(e.target.value);
              }}
              disabled={busy}
            />
          </label>
        )}

        <fieldset className="soc-suppress-matches" disabled={busy}>
          <legend>Match criteria</legend>
          <label className="soc-suppress-check">
            <input
              type="checkbox"
              checked={matchProcessPath}
              onChange={(e) => setMatchProcessPath(e.target.checked)}
            />
            Process / path
          </label>
          {matchProcessPath ? (
            <input
              className="form-input"
              value={processPathValue}
              onChange={(e) => setProcessPathValue(e.target.value)}
              placeholder="Process path or name"
            />
          ) : null}
          <label className="soc-suppress-check">
            <input
              type="checkbox"
              checked={matchParentProcess}
              onChange={(e) => setMatchParentProcess(e.target.checked)}
            />
            Parent process
          </label>
          {matchParentProcess ? (
            <input
              className="form-input"
              value={parentProcessValue}
              onChange={(e) => setParentProcessValue(e.target.value)}
            />
          ) : null}
          <label className="soc-suppress-check">
            <input
              type="checkbox"
              checked={matchFileHash}
              onChange={(e) => setMatchFileHash(e.target.checked)}
            />
            File hash
          </label>
          {matchFileHash ? (
            <input
              className="form-input"
              value={fileHashValue}
              onChange={(e) => setFileHashValue(e.target.value)}
              placeholder="SHA256 / MD5"
            />
          ) : null}
          <label className="soc-suppress-check">
            <input
              type="checkbox"
              checked={matchHostname}
              onChange={(e) => setMatchHostname(e.target.checked)}
            />
            Hostname match
          </label>
          {matchHostname ? (
            <input
              className="form-input"
              value={hostnameValue}
              onChange={(e) => setHostnameValue(e.target.value)}
            />
          ) : null}
        </fieldset>

        <label className="list-toolbar-field" style={{ marginTop: 12 }}>
          <span>Reason</span>
          <textarea
            className="form-input"
            rows={3}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            disabled={busy}
            placeholder="Why this pattern is safe to mute"
          />
        </label>

        <div className="modal-actions">
          <button type="button" className="btn btn-ghost" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={busy || loadingSeed}>
            {busy ? "Creating…" : "Create suppression"}
          </button>
        </div>
      </form>
    </div>
  );
}

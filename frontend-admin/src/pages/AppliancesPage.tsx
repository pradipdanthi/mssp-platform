import React, { useCallback, useEffect, useState, type FormEvent } from "react";
import { Appliance, Tenant, getAppliances, getTenants } from "../api/admin";
import {
  ActivationTokenMetadata,
  ApplianceCredentialMetadata,
  createActivationToken,
  getApplianceCredential,
  getOnPremTemplate,
  listActivationTokens,
  revokeActivationToken,
  rotateApplianceCredential,
} from "../api/appliances";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { useAdminQuery } from "../hooks/useAdminQuery";

function apiErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    if (typeof err.detail === "string") return err.detail;
    if (err.status === 403) return "Access denied for this action.";
    if (err.status === 404) return "Not found.";
    if (err.status === 409) return "This token cannot be revoked in its current status.";
  }
  return fallback;
}

export default function AppliancesPage() {
  const { status, data, errorMessage } = useAdminQuery(() => getAppliances(), []);

  return (
    <div>
      <h1 className="page-title">Appliances</h1>
      <p className="page-subtitle">
        Appliance list with credential visibility/rotation, plus tenant activation-token
        management.
      </p>

      {status === "loading" && <div className="state-message">Loading appliances...</div>}
      {status === "forbidden" && (
        <div className="state-message state-error">
          Access denied. Your account does not have permission to view appliances.
        </div>
      )}
      {status === "error" && <div className="state-message state-error">{errorMessage}</div>}

      {status === "success" && data && (
        data.appliances.length === 0 ? (
          <div className="state-message">No appliances yet.</div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Tenant</th>
                <th>Appliance</th>
                <th>Site</th>
                <th>Status</th>
                <th>Last Seen</th>
                <th>Health</th>
                <th>Credential</th>
              </tr>
            </thead>
            <tbody>
              {data.appliances.map((appliance) => (
                <ApplianceRow key={appliance.id} appliance={appliance} />
              ))}
            </tbody>
          </table>
        )
      )}

      {status === "success" && <ActivationTokensSection />}
    </div>
  );
}

function ApplianceRow({ appliance }: { appliance: Appliance }) {
  const [expanded, setExpanded] = useState(false);
  const [credential, setCredential] = useState<ApplianceCredentialMetadata | null>(null);
  const [credentialError, setCredentialError] = useState<string | null>(null);
  const [credentialLoading, setCredentialLoading] = useState(false);

  const [confirmingRotate, setConfirmingRotate] = useState(false);
  const [rotating, setRotating] = useState(false);
  const [rotateError, setRotateError] = useState<string | null>(null);

  // The raw key from a rotation lives only in this component's state -
  // never in sessionStorage/localStorage, never logged, and cleared as
  // soon as the one-time panel below is closed.
  const [newRawKey, setNewRawKey] = useState<string | null>(null);
  const [newKeyHint, setNewKeyHint] = useState<string | null>(null);
  const [copyConfirmed, setCopyConfirmed] = useState(false);

  async function loadCredential() {
    setCredentialLoading(true);
    setCredentialError(null);
    try {
      const result = await getApplianceCredential(appliance.id);
      setCredential(result);
    } catch (err) {
      setCredentialError(apiErrorMessage(err, "Could not load credential metadata."));
    } finally {
      setCredentialLoading(false);
    }
  }

  function handleExpandToggle() {
    const next = !expanded;
    setExpanded(next);
    if (next && !credential) {
      void loadCredential();
    }
  }

  async function handleRotateConfirmed() {
    setRotating(true);
    setRotateError(null);
    try {
      const result = await rotateApplianceCredential(appliance.id);
      setNewRawKey(result.appliance_api_key);
      setNewKeyHint(result.api_key_hint);
      setConfirmingRotate(false);
      void loadCredential();
    } catch (err) {
      setRotateError(apiErrorMessage(err, "Credential rotation failed. Please try again."));
    } finally {
      setRotating(false);
    }
  }

  function closeRotateResult() {
    setNewRawKey(null);
    setNewKeyHint(null);
    setCopyConfirmed(false);
  }

  async function handleCopy() {
    if (!newRawKey) return;
    try {
      await navigator.clipboard.writeText(newRawKey);
      setCopyConfirmed(true);
    } catch {
      setCopyConfirmed(false);
    }
  }

  return (
    <React.Fragment>
      <tr>
        <td>{appliance.tenant_name}</td>
        <td>{appliance.appliance_name}</td>
        <td>{appliance.site_name}</td>
        <td>
          <span className={`badge badge-${appliance.status}`}>{appliance.status}</span>
        </td>
        <td>{appliance.last_seen_at ?? "Never"}</td>
        <td>{appliance.health_status ?? "Unknown"}</td>
        <td>
          <button className="btn btn-ghost btn-small" type="button" onClick={handleExpandToggle}>
            {expanded ? "Hide" : "View"}
          </button>
        </td>
      </tr>

      {expanded && (
        <tr className="credential-row">
          <td colSpan={7}>
            {credentialLoading && <div className="state-message">Loading credential metadata...</div>}
            {credentialError && <div className="state-message state-error">{credentialError}</div>}

            {credential && (
              <div className="credential-panel">
                <div className="credential-grid">
                  <CredentialField
                    label="Has credential"
                    value={credential.has_appliance_api_key ? "Yes" : "No"}
                  />
                  <CredentialField label="Key hint" value={credential.appliance_api_key_hint ?? "—"} />
                  <CredentialField label="Created" value={credential.appliance_key_created_at ?? "—"} />
                  <CredentialField
                    label="Last used"
                    value={credential.appliance_key_last_used_at ?? "Never"}
                  />
                  <CredentialField label="Appliance status" value={credential.status} />
                  <CredentialField label="Last seen" value={credential.last_seen_at ?? "Never"} />
                </div>

                {!confirmingRotate && !newRawKey && (
                  <button className="btn btn-warning" type="button" onClick={() => setConfirmingRotate(true)}>
                    Rotate credential
                  </button>
                )}

                {confirmingRotate && (
                  <div className="confirm-box">
                    <p>
                      This will immediately invalidate this appliance&apos;s current API key. Any
                      device still using the old key will fail authentication (heartbeats, etc.)
                      until it is updated with the new key. Continue?
                    </p>
                    {rotateError && <div className="state-message state-error">{rotateError}</div>}
                    <div className="confirm-actions">
                      <button
                        className="btn btn-warning"
                        type="button"
                        onClick={handleRotateConfirmed}
                        disabled={rotating}
                      >
                        {rotating ? "Rotating..." : "Yes, rotate credential"}
                      </button>
                      <button
                        className="btn btn-ghost"
                        type="button"
                        onClick={() => setConfirmingRotate(false)}
                        disabled={rotating}
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}

                {newRawKey && (
                  <div className="one-time-secret-panel">
                    <p className="one-time-secret-warning">
                      Copy this key now. It will not be shown again.
                    </p>
                    <code className="one-time-secret-value">{newRawKey}</code>
                    <div className="one-time-secret-hint">Hint: {newKeyHint}</div>
                    <div className="confirm-actions">
                      <button className="btn btn-primary" type="button" onClick={handleCopy}>
                        {copyConfirmed ? "Copied!" : "Copy to clipboard"}
                      </button>
                      <button className="btn btn-ghost" type="button" onClick={closeRotateResult}>
                        Close and clear from screen
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </td>
        </tr>
      )}
    </React.Fragment>
  );
}

function ActivationTokensSection() {
  const { user } = useAuth();
  const canManageTokens = user?.role === "platform_admin";
  const canDownloadTemplate = user?.role === "platform_admin" || user?.role === "soc_manager";
  const [templateDownloading, setTemplateDownloading] = useState(false);
  const [templateError, setTemplateError] = useState<string | null>(null);

  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [tenantsError, setTenantsError] = useState<string | null>(null);
  const [tenantsLoading, setTenantsLoading] = useState(true);
  const [selectedTenantId, setSelectedTenantId] = useState("");

  const [tokens, setTokens] = useState<ActivationTokenMetadata[]>([]);
  const [tokensLoading, setTokensLoading] = useState(false);
  const [tokensError, setTokensError] = useState<string | null>(null);

  const [siteName, setSiteName] = useState("");
  const [expiresInHours, setExpiresInHours] = useState(24);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  // Raw activation token lives only here in component state - never in
  // sessionStorage/localStorage, never in a URL, never logged.
  const [rawToken, setRawToken] = useState<string | null>(null);
  const [rawTokenHint, setRawTokenHint] = useState<string | null>(null);
  const [copyConfirmed, setCopyConfirmed] = useState(false);

  const [revokingId, setRevokingId] = useState<string | null>(null);
  const [confirmRevokeId, setConfirmRevokeId] = useState<string | null>(null);
  const [revokeError, setRevokeError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setTenantsLoading(true);
    setTenantsError(null);
    getTenants()
      .then((result) => {
        if (cancelled) return;
        setTenants(result.tenants);
      })
      .catch((err) => {
        if (cancelled) return;
        setTenantsError(apiErrorMessage(err, "Could not load tenants."));
      })
      .finally(() => {
        if (!cancelled) setTenantsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const loadTokens = useCallback(async (tenantId: string) => {
    if (!tenantId) {
      setTokens([]);
      return;
    }
    setTokensLoading(true);
    setTokensError(null);
    setRevokeError(null);
    try {
      const result = await listActivationTokens(tenantId);
      setTokens(result.tokens);
    } catch (err) {
      setTokens([]);
      setTokensError(apiErrorMessage(err, "Could not load activation tokens."));
    } finally {
      setTokensLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!selectedTenantId) {
      setTokens([]);
      setTokensError(null);
      return;
    }
    void loadTokens(selectedTenantId);
  }, [selectedTenantId, loadTokens]);

  function clearRawTokenPanel() {
    setRawToken(null);
    setRawTokenHint(null);
    setCopyConfirmed(false);
  }

  function handleTenantChange(nextId: string) {
    clearRawTokenPanel();
    setCreateError(null);
    setRevokeError(null);
    setConfirmRevokeId(null);
    setSiteName("");
    setExpiresInHours(24);
    setSelectedTenantId(nextId);
  }

  async function handleCreate(event: FormEvent) {
    event.preventDefault();
    if (!canManageTokens || !selectedTenantId) return;
    setCreating(true);
    setCreateError(null);
    clearRawTokenPanel();
    try {
      const result = await createActivationToken(selectedTenantId, {
        site_name: siteName.trim(),
        expires_in_hours: expiresInHours,
      });
      // Keep raw token in local state only for one-time display.
      setRawToken(result.token);
      setRawTokenHint(result.metadata.token_hint);
      setSiteName("");
      setExpiresInHours(24);
      await loadTokens(selectedTenantId);
    } catch (err) {
      setCreateError(apiErrorMessage(err, "Could not create activation token."));
    } finally {
      setCreating(false);
    }
  }

  async function handleRevokeConfirmed(tokenId: string) {
    if (!canManageTokens) return;
    setRevokingId(tokenId);
    setRevokeError(null);
    try {
      await revokeActivationToken(tokenId);
      setConfirmRevokeId(null);
      if (selectedTenantId) {
        await loadTokens(selectedTenantId);
      }
    } catch (err) {
      setRevokeError(apiErrorMessage(err, "Could not revoke activation token."));
    } finally {
      setRevokingId(null);
    }
  }

  async function handleCopyRawToken() {
    if (!rawToken) return;
    try {
      await navigator.clipboard.writeText(rawToken);
      setCopyConfirmed(true);
    } catch {
      setCopyConfirmed(false);
    }
  }

  async function handleTemplateDownload() {
    if (!canDownloadTemplate) return;
    setTemplateDownloading(true);
    setTemplateError(null);
    try {
      const bundle = await getOnPremTemplate();
      const blob = new Blob([JSON.stringify(bundle, null, 2)], {
        type: "application/json",
      });
      const downloadUrl = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = downloadUrl;
      link.download = `${bundle.bundle_name}.${bundle.version}.json`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(downloadUrl);
    } catch (err) {
      setTemplateError(apiErrorMessage(err, "Could not download the on-prem template."));
    } finally {
      setTemplateDownloading(false);
    }
  }

  const selectedTenant = tenants.find((t) => t.id === selectedTenantId) ?? null;

  return (
    <section className="activation-tokens-section">
      <h2 className="section-title">Activation Tokens</h2>
      <p className="page-subtitle">
        Create and manage appliance activation tokens for a selected tenant. The raw token is shown
        only once at creation time.
      </p>

      {canDownloadTemplate && (
        <button
          className="btn btn-primary"
          type="button"
          onClick={handleTemplateDownload}
          disabled={templateDownloading}
        >
          {templateDownloading ? "Preparing template..." : "Download on-prem template"}
        </button>
      )}
      {templateError && <div className="state-message state-error">{templateError}</div>}

      {!canManageTokens && (
        <div className="state-message activation-readonly-note">
          Read-only view. Only platform_admin can create or revoke activation tokens.
        </div>
      )}

      {tenantsLoading && <div className="state-message">Loading tenants...</div>}
      {tenantsError && <div className="state-message state-error">{tenantsError}</div>}

      {!tenantsLoading && !tenantsError && (
        <div className="activation-tenant-picker">
          <label className="form-label" htmlFor="activation-tenant">
            Tenant
          </label>
          <select
            id="activation-tenant"
            className="form-input activation-tenant-select"
            value={selectedTenantId}
            onChange={(e) => handleTenantChange(e.target.value)}
          >
            <option value="">Select a tenant...</option>
            {tenants.map((tenant) => (
              <option key={tenant.id} value={tenant.id}>
                {tenant.name} ({tenant.short_code})
              </option>
            ))}
          </select>
        </div>
      )}

      {selectedTenantId && (
        <>
          {canManageTokens && (
            <form className="activation-create-form" onSubmit={handleCreate}>
              <div className="activation-create-grid">
                <div>
                  <label className="form-label" htmlFor="activation-site-name">
                    Site name
                  </label>
                  <input
                    id="activation-site-name"
                    className="form-input"
                    type="text"
                    value={siteName}
                    onChange={(e) => setSiteName(e.target.value)}
                    required
                    minLength={1}
                    maxLength={200}
                    placeholder="e.g. Main HQ"
                  />
                </div>
                <div>
                  <label className="form-label" htmlFor="activation-expires-hours">
                    Expires in (hours)
                  </label>
                  <input
                    id="activation-expires-hours"
                    className="form-input"
                    type="number"
                    min={1}
                    max={720}
                    value={expiresInHours}
                    onChange={(e) => setExpiresInHours(Number(e.target.value))}
                    required
                  />
                </div>
              </div>
              {createError && <div className="state-message state-error">{createError}</div>}
              <button className="btn btn-primary" type="submit" disabled={creating || !siteName.trim()}>
                {creating ? "Creating..." : "Create activation token"}
              </button>
            </form>
          )}

          {rawToken && (
            <div className="one-time-secret-panel">
              <p className="one-time-secret-warning">
                Copy this token now. It will not be shown again.
              </p>
              <code className="one-time-secret-value">{rawToken}</code>
              {rawTokenHint && <div className="one-time-secret-hint">Hint: {rawTokenHint}</div>}
              {selectedTenant && (
                <div className="one-time-secret-hint">
                  Tenant: {selectedTenant.name} ({selectedTenant.short_code})
                </div>
              )}
              <div className="confirm-actions">
                <button className="btn btn-primary" type="button" onClick={handleCopyRawToken}>
                  {copyConfirmed ? "Copied!" : "Copy to clipboard"}
                </button>
                <button className="btn btn-ghost" type="button" onClick={clearRawTokenPanel}>
                  Close and clear from screen
                </button>
              </div>
            </div>
          )}

          {tokensLoading && <div className="state-message">Loading activation tokens...</div>}
          {tokensError && <div className="state-message state-error">{tokensError}</div>}
          {revokeError && <div className="state-message state-error">{revokeError}</div>}

          {!tokensLoading && !tokensError && tokens.length === 0 && (
            <div className="state-message">No activation tokens for this tenant yet.</div>
          )}

          {!tokensLoading && tokens.length > 0 && (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Token ID</th>
                  <th>Site</th>
                  <th>Hint</th>
                  <th>Status</th>
                  <th>Expires</th>
                  <th>Used</th>
                  <th>Created</th>
                  {canManageTokens && <th>Actions</th>}
                </tr>
              </thead>
              <tbody>
                {tokens.map((tok) => {
                  const canRevoke = canManageTokens && tok.status === "pending";
                  return (
                    <tr key={tok.id}>
                      <td title={tok.id}>{tok.id.slice(0, 8)}...</td>
                      <td>{tok.site_name}</td>
                      <td>{tok.token_hint ?? "—"}</td>
                      <td>
                        <span className={`badge badge-${tok.status}`}>{tok.status}</span>
                      </td>
                      <td>{tok.expires_at ?? "—"}</td>
                      <td>{tok.used_at ?? "—"}</td>
                      <td>{tok.created_at}</td>
                      {canManageTokens && (
                        <td>
                          {confirmRevokeId === tok.id ? (
                            <div className="confirm-actions">
                              <button
                                className="btn btn-warning btn-small"
                                type="button"
                                disabled={revokingId === tok.id}
                                onClick={() => handleRevokeConfirmed(tok.id)}
                              >
                                {revokingId === tok.id ? "Revoking..." : "Confirm revoke"}
                              </button>
                              <button
                                className="btn btn-ghost btn-small"
                                type="button"
                                disabled={revokingId === tok.id}
                                onClick={() => setConfirmRevokeId(null)}
                              >
                                Cancel
                              </button>
                            </div>
                          ) : (
                            <button
                              className="btn btn-ghost btn-small"
                              type="button"
                              disabled={!canRevoke}
                              title={
                                canRevoke
                                  ? "Revoke this pending activation token"
                                  : "Only pending tokens can be revoked"
                              }
                              onClick={() => setConfirmRevokeId(tok.id)}
                            >
                              Revoke
                            </button>
                          )}
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </>
      )}
    </section>
  );
}

function CredentialField({ label, value }: { label: string; value: string }) {
  return (
    <div className="credential-field">
      <div className="credential-field-label">{label}</div>
      <div className="credential-field-value">{value}</div>
    </div>
  );
}

import React, { useState } from "react";
import { Appliance, getAppliances } from "../api/admin";
import {
  ApplianceCredentialMetadata,
  getApplianceCredential,
  rotateApplianceCredential,
} from "../api/appliances";
import { ApiError } from "../api/client";
import { useAdminQuery } from "../hooks/useAdminQuery";

export default function AppliancesPage() {
  const { status, data, errorMessage } = useAdminQuery(() => getAppliances(), []);

  return (
    <div>
      <h1 className="page-title">Appliances</h1>
      <p className="page-subtitle">
        Read-only appliance list, with credential visibility and rotation (KB-017).
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
      setCredentialError(
        err instanceof ApiError && typeof err.detail === "string"
          ? err.detail
          : "Could not load credential metadata."
      );
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
      // Refresh the safe metadata (hint/created_at) shown above - the raw
      // key itself is never re-fetched or persisted, it only exists in
      // newRawKey until closeRotateResult() clears it.
      void loadCredential();
    } catch (err) {
      setRotateError(
        err instanceof ApiError && typeof err.detail === "string"
          ? err.detail
          : "Credential rotation failed. Please try again."
      );
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

function CredentialField({ label, value }: { label: string; value: string }) {
  return (
    <div className="credential-field">
      <div className="credential-field-label">{label}</div>
      <div className="credential-field-value">{value}</div>
    </div>
  );
}

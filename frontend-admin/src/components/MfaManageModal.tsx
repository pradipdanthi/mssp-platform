import { AdminUser } from "../api/admin";

type Props = {
  user: AdminUser;
  enforceResult: { secret: string; otpauth_url: string } | null;
  busy: boolean;
  error: string | null;
  onClose: () => void;
  onReset: () => void;
  onEnforce: () => void;
};

export default function MfaManageModal({
  user,
  enforceResult,
  busy,
  error,
  onClose,
  onReset,
  onEnforce,
}: Props) {
  const qrSrc = enforceResult
    ? `https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(
        enforceResult.otpauth_url
      )}`
    : null;

  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="modal-panel management-panel"
        role="dialog"
        aria-labelledby="mfa-manage-title"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="mfa-manage-title" className="section-title" style={{ marginTop: 0 }}>
          MFA — {user.full_name}
        </h2>
        <p className="page-subtitle">{user.email}</p>
        <p>
          Status:{" "}
          <span className={`badge ${user.is_mfa_enabled ? "badge-active" : "badge-inactive"}`}>
            {user.is_mfa_enabled ? "ENABLED" : "DISABLED"}
          </span>
        </p>
        {user.mfa_updated_at && (
          <p className="page-subtitle">Last MFA change: {user.mfa_updated_at}</p>
        )}

        {enforceResult && (
          <div style={{ marginTop: "1rem" }}>
            <p className="page-subtitle">
              Scan this QR code or enter the secret manually in the user&apos;s authenticator app.
            </p>
            {qrSrc && (
              <img
                src={qrSrc}
                alt="MFA QR code"
                width={200}
                height={200}
                style={{ display: "block", margin: "0.5rem 0 1rem" }}
              />
            )}
            <label className="form-label">
              Secret key
              <input className="form-input" readOnly value={enforceResult.secret} />
            </label>
            <label className="form-label">
              otpauth URL
              <input className="form-input" readOnly value={enforceResult.otpauth_url} />
            </label>
          </div>
        )}

        {error && <div className="form-error">{error}</div>}

        <div className="confirm-actions" style={{ marginTop: "1rem" }}>
          <button className="btn btn-primary" type="button" disabled={busy} onClick={onEnforce}>
            {busy ? "Working..." : enforceResult ? "Regenerate MFA" : "Setup / Enforce MFA"}
          </button>
          <button
            className="btn btn-ghost"
            type="button"
            disabled={busy || !user.is_mfa_enabled}
            onClick={onReset}
          >
            Reset MFA
          </button>
          <button className="btn btn-ghost" type="button" disabled={busy} onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

import { FormEvent, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  clearMfaSetupToken,
  getStoredMfaSetupToken,
  mfaCompleteSetup,
  mfaSetupSession,
} from "../api/auth";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { useBrand } from "../config/BrandContext";

type Step = 1 | 2 | 3;

export default function MfaSetupPage() {
  const brand = useBrand();
  const navigate = useNavigate();
  const { establishSessionFromToken } = useAuth();
  const [step, setStep] = useState<Step>(1);
  const [setupToken] = useState<string | null>(getStoredMfaSetupToken());
  const [secret, setSecret] = useState("");
  const [otpauthUri, setOtpauthUri] = useState("");
  const [verifyCode, setVerifyCode] = useState("");
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!setupToken) {
      navigate("/login", { replace: true });
      return;
    }
    mfaSetupSession(setupToken)
      .then((session) => {
        setSecret(session.secret);
        setOtpauthUri(session.otpauth_uri);
      })
      .catch(() => {
        clearMfaSetupToken();
        navigate("/login", { replace: true });
      })
      .finally(() => setLoading(false));
  }, [setupToken, navigate]);

  const qrSrc = otpauthUri
    ? `https://api.qrserver.com/v1/create-qr-code/?size=220x220&data=${encodeURIComponent(otpauthUri)}`
    : null;

  async function handleVerify(event: FormEvent) {
    event.preventDefault();
    if (!setupToken || verifyCode.trim().length < 6) return;
    setSubmitting(true);
    setError(null);
    try {
      const result = await mfaCompleteSetup(setupToken, verifyCode.trim());
      setRecoveryCodes(result.recovery_codes);
      setStep(3);
      await establishSessionFromToken(result);
      clearMfaSetupToken();
    } catch (err) {
      setError(err instanceof ApiError && typeof err.detail === "string" ? err.detail : "Invalid code.");
    } finally {
      setSubmitting(false);
    }
  }

  function copyRecoveryCodes() {
    void navigator.clipboard.writeText(recoveryCodes.join("\n"));
  }

  function downloadRecoveryCodes() {
    const blob = new Blob(
      [
        `${brand.portalName} — MFA recovery codes\n`,
        `Generated: ${new Date().toISOString()}\n\n`,
        ...recoveryCodes.map((c) => `${c}\n`),
        "\nStore these securely. Each code works once.\n",
      ],
      { type: "text/plain" }
    );
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "kevantic-mfa-recovery-codes.txt";
    anchor.click();
    URL.revokeObjectURL(url);
  }

  if (loading) {
    return <div className="app-loading">Preparing MFA setup...</div>;
  }

  return (
    <main className="kevantic-login">
      <section className="kevantic-login__card" aria-label="MFA setup">
        <div className="kevantic-login__card-inner">
          <header className="kevantic-login__header">
            <h1 className="kevantic-login__title">
              SECURE YOUR
              <span>ACCOUNT</span>
            </h1>
            <p className="kevantic-login__subtitle">
              Multi-factor authentication is required for your organization.
            </p>
          </header>

          {step === 1 && (
            <div className="kevantic-login__form">
              <p className="kevantic-login__subtitle">
                <strong>Step 1:</strong> Scan this QR code with Google Authenticator, Microsoft
                Authenticator, or another TOTP app.
              </p>
              {qrSrc ? (
                <img
                  src={qrSrc}
                  alt="MFA QR code"
                  width={220}
                  height={220}
                  style={{ display: "block", margin: "1rem auto" }}
                />
              ) : null}
              <label className="kevantic-login__field">
                <span>Manual entry secret</span>
                <input className="form-input" readOnly value={secret} />
              </label>
              <button className="kevantic-login__button" type="button" onClick={() => setStep(2)}>
                <span>Continue to verification</span>
              </button>
            </div>
          )}

          {step === 2 && (
            <form className="kevantic-login__form" onSubmit={handleVerify} noValidate>
              <p className="kevantic-login__subtitle">
                <strong>Step 2:</strong> Enter the 6-digit code from your authenticator app.
              </p>
              <div className="kevantic-login__field">
                <label htmlFor="setup-verify-code">Verification code</label>
                <input
                  id="setup-verify-code"
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  pattern="[0-9]{6}"
                  maxLength={8}
                  value={verifyCode}
                  onChange={(e) => setVerifyCode(e.target.value)}
                  disabled={submitting}
                  required
                />
              </div>
              {error ? (
                <div className="kevantic-login__error" role="alert">
                  {error}
                </div>
              ) : null}
              <button className="kevantic-login__button" type="submit" disabled={submitting}>
                <span>{submitting ? "Verifying..." : "Verify & generate backup codes"}</span>
              </button>
              <button
                className="btn btn-ghost"
                type="button"
                style={{ marginTop: "0.75rem", width: "100%" }}
                onClick={() => setStep(1)}
              >
                Back to QR code
              </button>
            </form>
          )}

          {step === 3 && (
            <div className="kevantic-login__form">
              <p className="kevantic-login__subtitle">
                <strong>Step 3:</strong> Save these backup recovery codes. Each can be used once if
                you lose your phone.
              </p>
              <ul
                style={{
                  listStyle: "none",
                  padding: 0,
                  margin: "1rem 0",
                  fontFamily: "monospace",
                  fontSize: "1.05rem",
                }}
              >
                {recoveryCodes.map((code) => (
                  <li key={code} style={{ padding: "0.25rem 0" }}>
                    {code}
                  </li>
                ))}
              </ul>
              <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                <button className="btn btn-ghost" type="button" onClick={copyRecoveryCodes}>
                  Copy
                </button>
                <button className="btn btn-ghost" type="button" onClick={downloadRecoveryCodes}>
                  Download TXT
                </button>
              </div>
              <button
                className="kevantic-login__button"
                type="button"
                style={{ marginTop: "1rem" }}
                onClick={() => navigate("/dashboard", { replace: true })}
              >
                <span>Continue to dashboard</span>
              </button>
            </div>
          )}
        </div>
      </section>
    </main>
  );
}

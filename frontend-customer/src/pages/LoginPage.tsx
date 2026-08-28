import { FormEvent, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { useBrand } from "../config/BrandContext";
import { storeMfaSetupToken } from "../api/auth";
import KevanticLogin from "../components/KevanticLogin";

export default function LoginPage() {
  const { token, loading, login, completeMfaLogin, error, clearError } = useAuth();
  const brand = useBrand();
  const navigate = useNavigate();
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [mfaToken, setMfaToken] = useState<string | null>(null);
  const [mfaCode, setMfaCode] = useState("");

  if (loading) {
    return <div className="app-loading">Loading {brand.portalName}...</div>;
  }

  if (token) {
    return <Navigate to="/dashboard" replace />;
  }

  async function handleCustomerLogin(email: string, password: string) {
    setFormError(null);
    clearError();
    setSubmitting(true);
    try {
      const result = await login(email, password);
      if (result.mfaRequired && result.mfaToken) {
        setMfaToken(result.mfaToken);
        setMfaCode("");
      } else if (result.mfaSetupRequired && result.setupToken) {
        storeMfaSetupToken(result.setupToken);
        navigate("/mfa-setup", { replace: true });
      }
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 0 || err.status === 502 || err.status === 503) {
          setFormError("Cannot reach the login service. Please try again in a moment.");
        } else if (typeof err.detail === "string") {
          setFormError(err.detail);
        } else {
          setFormError("Invalid email or password.");
        }
      } else {
        setFormError("Invalid email or password.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  async function handleMfaSubmit(event: FormEvent) {
    event.preventDefault();
    if (!mfaToken || mfaCode.trim().length < 6) return;
    setFormError(null);
    clearError();
    setSubmitting(true);
    try {
      await completeMfaLogin(mfaToken, mfaCode.trim());
    } catch (err) {
      if (err instanceof ApiError && typeof err.detail === "string") {
        setFormError(err.detail);
      } else {
        setFormError(error || "Invalid MFA code.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  if (mfaToken) {
    return (
      <main className="kevantic-login">
        <section className="kevantic-login__card" aria-label="MFA verification">
          <div className="kevantic-login__card-inner">
            <header className="kevantic-login__header">
              <h1 className="kevantic-login__title">
                MULTI-FACTOR
                <span>AUTHENTICATION</span>
              </h1>
              <p className="kevantic-login__subtitle">
                Enter your 6-digit authenticator code or a backup recovery code (XXXX-XXXX).
              </p>
            </header>
            <form className="kevantic-login__form" onSubmit={handleMfaSubmit} noValidate>
              <div className="kevantic-login__field">
                <label htmlFor="customer-mfa-code">Authentication code</label>
                <input
                  id="customer-mfa-code"
                  name="mfa_code"
                  type="text"
                  inputMode="text"
                  autoComplete="one-time-code"
                  maxLength={16}
                  value={mfaCode}
                  onChange={(e) => setMfaCode(e.target.value)}
                  disabled={submitting}
                  required
                />
              </div>
              {(formError || error) && (
                <div className="kevantic-login__error" role="alert">
                  {formError || error}
                </div>
              )}
              <button className="kevantic-login__button" type="submit" disabled={submitting}>
                <span>{submitting ? "Verifying..." : "Verify & Sign In"}</span>
              </button>
              <button
                className="btn btn-ghost"
                type="button"
                style={{ marginTop: "0.75rem", width: "100%" }}
                disabled={submitting}
                onClick={() => {
                  setMfaToken(null);
                  setMfaCode("");
                  setFormError(null);
                  clearError();
                }}
              >
                Back to password login
              </button>
            </form>
          </div>
        </section>
      </main>
    );
  }

  return (
    <KevanticLogin
      portal="customer"
      logoSrc={brand.logo.logoSrc}
      backgroundSrc="/brand/kevantic-login-background.webp"
      loading={submitting}
      error={formError || error}
      onLogin={handleCustomerLogin}
    />
  );
}

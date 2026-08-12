import { useState, type FormEvent } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { useBrand } from "../config/BrandContext";
import KestrelFalconShieldLogo from "../components/brand/KestrelFalconShieldLogo";
import KestrelSecurityWatermark from "../components/brand/KestrelSecurityWatermark";

export default function LoginPage() {
  const { token, loading, login } = useAuth();
  const brand = useBrand();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  if (loading) {
    return <div className="app-loading">Loading {brand.portalName}...</div>;
  }

  if (token) {
    return <Navigate to="/dashboard" replace />;
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setFormError(null);
    setSubmitting(true);
    try {
      await login(email, password);
    } catch {
      setFormError("Invalid email or password.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="login-page">
      <KestrelSecurityWatermark />
      <div className="login-hero" role="main">
        <div className="login-chest-panel">
          <div className="login-chest-brand">
            <KestrelFalconShieldLogo size={280} className="login-brand-logo" title="Kevantic Cyber Security" />
            <span className="login-brand-portal">{brand.portalName}</span>
          </div>
          <p className="login-subtitle">{brand.tagline}</p>

          <form className="login-form" onSubmit={handleSubmit}>
            <label className="form-label" htmlFor="email">
              Email
            </label>
            <input
              id="email"
              className="form-input"
              type="email"
              autoComplete="username"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />

            <label className="form-label" htmlFor="password">
              Password
            </label>
            <input
              id="password"
              className="form-input"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />

            {formError && <div className="form-error">{formError}</div>}

            <button className="btn btn-primary login-submit" type="submit" disabled={submitting}>
              {submitting ? "Signing in..." : "Sign in"}
            </button>
          </form>

          <p className="login-support">
            Support:{" "}
            <a href={`mailto:${brand.supportEmail}`}>{brand.supportEmail}</a>
          </p>
          <p className="login-legal">{brand.footerCopyright}</p>
        </div>
      </div>
    </div>
  );
}

import { useState, type FormEvent } from "react";
import { Navigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { useBrand } from "../config/BrandContext";
import KestrelSecurityWatermark from "../components/brand/KestrelSecurityWatermark";
import EagleOpenWings from "../assets/images/kestrel_eagle_open_wings.png";

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

  return (
    <div className="login-page">
      <KestrelSecurityWatermark />
      <div className="login-hero" role="main">
        <img
          src={EagleOpenWings}
          alt=""
          className="login-eagle"
          draggable={false}
          decoding="async"
        />
        <div className="login-chest-panel">
          <div className="login-chest-brand">
            <span className="login-brand-product">{brand.productName}</span>
            <span className="login-brand-portal">{brand.portalName}</span>
            <span className="login-company">by {brand.companyName}</span>
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
          <p className="login-legal">
            {brand.companyName} and {brand.productName} are business/service brands operated by{" "}
            {brand.legalEntityName}.
          </p>
        </div>
      </div>
    </div>
  );
}

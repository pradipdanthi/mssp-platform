import { useState } from "react";
import { Navigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { useBrand } from "../config/BrandContext";
import KevanticLogin from "../components/KevanticLogin";

export default function LoginPage() {
  const { token, loading, login } = useAuth();
  const brand = useBrand();
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  if (loading) {
    return <div className="app-loading">Loading {brand.portalName}...</div>;
  }

  if (token) {
    return <Navigate to="/dashboard" replace />;
  }

  async function handleCustomerLogin(email: string, password: string) {
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
    <KevanticLogin
      portal="customer"
      logoSrc={brand.logo.logoSrc}
      backgroundSrc="/brand/kevantic-login-background.webp"
      loading={submitting}
      error={formError}
      onLogin={handleCustomerLogin}
    />
  );
}

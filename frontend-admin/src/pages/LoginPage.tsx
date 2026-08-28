import { useState } from "react";
import { Navigate } from "react-router-dom";
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

  async function handleAdminLogin(email: string, password: string) {
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
    <KevanticLogin
      portal="admin"
      logoSrc={brand.logo.logoSrc}
      backgroundSrc="/brand/kevantic-login-background.webp"
      loading={submitting}
      error={formError}
      onLogin={handleAdminLogin}
    />
  );
}

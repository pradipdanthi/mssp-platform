import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { useBrand } from "../config/BrandContext";
import Layout from "./Layout";

export default function ProtectedRoute({ children }: { children: ReactNode }) {
  const { token, user, loading } = useAuth();
  const brand = useBrand();

  if (loading) {
    return <div className="app-loading">Loading {brand.portalName}...</div>;
  }

  if (!token || !user) {
    return <Navigate to="/login" replace />;
  }

  return <Layout>{children}</Layout>;
}

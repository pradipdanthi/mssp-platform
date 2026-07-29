import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { useBrand } from "../config/BrandContext";
import KestrelFalconShieldLogo from "./brand/KestrelFalconShieldLogo";
import KestrelSecurityWatermark from "./brand/KestrelSecurityWatermark";
import EngineStatusRibbon from "./EngineStatusRibbon";
import GlobalSearch from "./GlobalSearch";

const NAV_ITEMS = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/alerts", label: "Alerts" },
  { to: "/incidents", label: "Incidents" },
  { to: "/assets", label: "Assets" },
  { to: "/services", label: "Services" },
  { to: "/vulnerabilities", label: "Vulnerabilities" },
  { to: "/recommendations", label: "Recommendations" },
  { to: "/reports", label: "Reports" },
  { to: "/notifications", label: "Notifications" },
  { to: "/users", label: "User Management" },
  { to: "/audit", label: "Audit" },
  { to: "/account", label: "Account" },
];

export default function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const brand = useBrand();

  return (
    <div className="app-shell">
      <KestrelSecurityWatermark />
      <aside className="sidebar">
        <div className="sidebar-brand">
          <KestrelFalconShieldLogo
            size={118}
            className="sidebar-brand-logo"
            title={brand.productName}
          />
          <div className="sidebar-brand-copy">
            <span className="sidebar-brand-product">{brand.productName}</span>
            <span className="sidebar-brand-text">Customer Portal</span>
            <span className="sidebar-brand-company">by {brand.companyName}</span>
          </div>
        </div>
        <nav className="sidebar-nav">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => "sidebar-nav-link" + (isActive ? " active" : "")}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <footer className="sidebar-footer">
          <p className="sidebar-footer-legal">
            {brand.companyName} and {brand.productName} are business/service brands operated by{" "}
            {brand.legalEntityName}.
          </p>
        </footer>
      </aside>
      <div className="app-main">
        <header className="app-header sentinel-header">
          <div className="app-header-left">
            <div className="app-header-title">
              {user?.tenant_name ? user.tenant_name : brand.portalName}
            </div>
            <div className="app-header-widgets">
              <GlobalSearch />
              <EngineStatusRibbon />
            </div>
          </div>
          <div className="app-header-user">
            {user && (
              <span className="app-header-user-info">
                <span className="app-header-user-name">{user.full_name}</span>
                <span className="app-header-user-meta">
                  {user.email}
                  {user.tenant_short_code ? ` · ${user.tenant_short_code}` : ""}
                  {user.role ? ` · ${user.role}` : ""}
                </span>
              </span>
            )}
            <button className="btn btn-ghost" onClick={logout} type="button">
              Logout
            </button>
          </div>
        </header>
        <main className="app-content">{children}</main>
      </div>
    </div>
  );
}

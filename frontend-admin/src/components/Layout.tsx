import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { useBrand } from "../config/BrandContext";
import KestrelFalconShieldLogo from "./brand/KestrelFalconShieldLogo";
import KestrelSecurityWatermark from "./brand/KestrelSecurityWatermark";
import EngineStatusRibbon from "./EngineStatusRibbon";
import GlobalSearch from "./GlobalSearch";
import TenantSwitcher from "./TenantSwitcher";
import NavIcon from "./icons/NavIcon";

const NAV_ITEMS = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/tenants", label: "Customers" },
  { to: "/users", label: "Users" },
  { to: "/appliances", label: "Appliances" },
  { to: "/retrospective-hunts", label: "Retro Hunts" },
  { to: "/threat-intel", label: "Threat Intel" },
  { to: "/ai-assistant", label: "AI Assistant" },
  { to: "/assets", label: "Assets" },
  { to: "/alerts", label: "Alerts" },
  { to: "/incidents", label: "Incidents" },
  { to: "/vulnerabilities", label: "Vulnerabilities" },
  { to: "/recommendations", label: "Recommendations" },
  { to: "/reports", label: "Reports" },
  { to: "/notifications", label: "Notifications" },
  { to: "/audit", label: "Audit" },
  { to: "/service-requests", label: "Service Requests" },
  { to: "/services", label: "Service Catalog" },
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
            size={200}
            className="sidebar-brand-logo"
            title="Kevantic Cyber Security"
          />
          <div className="sidebar-brand-copy">
            <span className="sidebar-brand-portal">{brand.portalName}</span>
          </div>
        </div>
        <nav className="sidebar-nav" aria-label="Primary">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => "sidebar-nav-link" + (isActive ? " active" : "")}
            >
              <NavIcon to={item.to} />
              <span className="sidebar-nav-label">{item.label}</span>
            </NavLink>
          ))}
        </nav>
        <footer className="sidebar-footer">
          <p className="sidebar-footer-legal">{brand.footerCopyright}</p>
        </footer>
      </aside>
      <div className="app-main">
        <header className="app-header sentinel-header">
          <div className="app-header-left">
            <div className="app-header-title">{brand.portalName}</div>
            <div className="app-header-widgets">
              <TenantSwitcher />
              <GlobalSearch />
              <EngineStatusRibbon />
            </div>
          </div>
          <div className="app-header-user">
            {user && (
              <span className="app-header-user-info">
                <span className="app-header-user-name">{user.full_name}</span>
                <span className="app-header-user-meta">
                  {user.email} &middot; {user.role}
                </span>
              </span>
            )}
            <button className="btn btn-ghost" onClick={logout} type="button">
              Logout
            </button>
          </div>
        </header>
        <main className="app-content sentinel-canvas">{children}</main>
      </div>
    </div>
  );
}

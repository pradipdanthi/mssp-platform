import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { useBrand } from "../config/BrandContext";
import { useCustomerEntitlements } from "../config/EntitlementsContext";
import { buildCustomerNavItems } from "../config/navEntitlements";
import { normalizeTier } from "../config/tierConfig";
import { TierUpgradeBadge } from "./TierUpgradeBadge";
import KestrelFalconShieldLogo from "./brand/KestrelFalconShieldLogo";
import KestrelSecurityWatermark from "./brand/KestrelSecurityWatermark";
import EngineStatusRibbon from "./EngineStatusRibbon";
import GlobalSearch from "./GlobalSearch";
import NavIcon from "./icons/NavIcon";

export default function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const brand = useBrand();
  const { entitlements, loading: entitlementsLoading } = useCustomerEntitlements();
  const navItems = buildCustomerNavItems(entitlementsLoading ? null : entitlements);
  const tier = normalizeTier(entitlements?.subscription_tier || user?.subscription_tier);

  return (
    <div className="app-shell" data-portal="customer">
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
          {navItems.map((item) =>
            item.locked ? (
              <div key={item.to} className="sidebar-nav-link sidebar-nav-link-locked">
                <NavIcon to={item.to} />
                <div className="sidebar-nav-link-body">
                  <span className="sidebar-nav-label">{item.label}</span>
                  {item.requiredTier ? (
                    <TierUpgradeBadge
                      requiredTier={item.requiredTier}
                      className="tier-nav-badge"
                      compact
                    />
                  ) : null}
                </div>
              </div>
            ) : (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) => "sidebar-nav-link" + (isActive ? " active" : "")}
              >
                <NavIcon to={item.to} />
                <span className="sidebar-nav-label">{item.label}</span>
              </NavLink>
            )
          )}
        </nav>
        <footer className="sidebar-footer">
          <p className="sidebar-footer-legal">{brand.footerCopyright}</p>
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
                  {tier ? ` · ${tier}` : ""}
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

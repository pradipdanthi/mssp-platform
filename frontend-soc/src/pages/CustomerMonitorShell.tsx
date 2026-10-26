import { useEffect, useMemo, useRef, useState } from "react";
import { Link, NavLink, Outlet, useNavigate, useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { getTenants } from "../api/soc";
import { useAuth } from "../auth/AuthContext";
import { setStoredTenantFilter } from "../parity/components/TenantSwitcher";

type TenantHit = { id: string; name: string; short_code: string };

/**
 * Enterprise customer console shell — Overview + Alerts + Incidents + Vulns + Patch Gaps.
 * No Tia chat / no global live feed. Tenant scope locked for Admin-parity list pages.
 */
export default function CustomerMonitorShell() {
  const { shortCode } = useParams<{ shortCode: string }>();
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [tenant, setTenant] = useState<TenantHit | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const prevScopeRef = useRef<string>("all");

  useEffect(() => {
    if (!shortCode) return;
    let cancelled = false;
    try {
      prevScopeRef.current = localStorage.getItem("mssp.admin.tenantFilter") || "all";
    } catch {
      prevScopeRef.current = "all";
    }
    getTenants()
      .then((r) => {
        const hit = (r.tenants || []).find(
          (t) => t.short_code.toLowerCase() === shortCode.toLowerCase()
        );
        if (!hit) {
          setErr("Customer not found");
          return;
        }
        if (cancelled) return;
        setTenant({ id: hit.id, name: hit.name, short_code: hit.short_code });
        setErr(null);
        setStoredTenantFilter(hit.id);
      })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) logout();
        else setErr("Unable to load customer");
      });
    return () => {
      cancelled = true;
      setStoredTenantFilter(prevScopeRef.current);
    };
  }, [shortCode, logout]);

  const base = useMemo(
    () => `/monitor/${encodeURIComponent(shortCode || "")}`,
    [shortCode]
  );

  function openOnMonitor() {
    window.open(`${window.location.origin}${base}`, `soc-monitor-${shortCode}`, "noopener,noreferrer");
  }

  return (
    <div className="monitor-page">
      <header className="monitor-top">
        <div>
          <p className="muted">Customer SOC console · scoped · no global feed / chat</p>
          <h1>
            {tenant?.name || shortCode}{" "}
            <span className="muted">({tenant?.short_code || shortCode})</span>
          </h1>
          <p className="muted">{user?.full_name || user?.email}</p>
        </div>
        <div className="workbench-filters">
          <button type="button" className="btn btn-ghost" onClick={openOnMonitor}>
            Open on monitor
          </button>
          <button type="button" className="btn btn-ghost" onClick={() => navigate("/customers")}>
            All customers
          </button>
          <Link className="btn btn-ghost" to="/">
            Console home
          </Link>
        </div>
      </header>

      <nav className="monitor-nav" aria-label="Customer sections">
        <NavLink to={base} end className={({ isActive }) => (isActive ? "is-active" : undefined)}>
          Overview
        </NavLink>
        <NavLink to={`${base}/alerts`} className={({ isActive }) => (isActive ? "is-active" : undefined)}>
          Alerts
        </NavLink>
        <NavLink
          to={`${base}/incidents`}
          className={({ isActive }) => (isActive ? "is-active" : undefined)}
        >
          Incidents
        </NavLink>
        <NavLink
          to={`${base}/vulnerabilities`}
          className={({ isActive }) => (isActive ? "is-active" : undefined)}
        >
          Vulnerabilities
        </NavLink>
        <NavLink
          to={`${base}/patch-gaps`}
          className={({ isActive }) => (isActive ? "is-active" : undefined)}
        >
          Patch gaps
        </NavLink>
      </nav>

      {err && <div className="err" style={{ padding: "0.75rem 1rem" }}>{err}</div>}

      <div className="monitor-body">
        <Outlet context={{ tenant, shortCode, base }} />
      </div>
    </div>
  );
}

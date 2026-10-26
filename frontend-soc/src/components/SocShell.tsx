import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import SocTiles, { type SocKpis, type TileId } from "./SocTiles";
import { useAuth } from "../auth/AuthContext";
import { getActivity, getTenants } from "../api/soc";
import { ApiError } from "../api/client";

function tileFromPath(pathname: string): TileId {
  if (pathname.startsWith("/alerts")) return "alert";
  if (pathname.startsWith("/incidents")) return "incident";
  if (pathname.startsWith("/customers")) return "customers";
  if (pathname.startsWith("/events")) return "event";
  if (pathname.startsWith("/vulnerabilities")) return "vulnerability";
  if (pathname.startsWith("/patch-gaps")) return "patch_gap";
  return "all";
}

export default function SocShell() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [kpis, setKpis] = useState<SocKpis | null>(null);
  const active = tileFromPath(location.pathname);

  useEffect(() => {
    let cancelled = false;
    Promise.all([getActivity(40), getTenants()])
      .then(([act, ten]) => {
        if (cancelled) return;
        const base = { ...(act.kpis || {}) } as SocKpis;
        base.customers = (ten.tenants || []).length;
        setKpis(base);
      })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) logout();
      });
    return () => {
      cancelled = true;
    };
  }, [logout, location.pathname]);

  function onSelectTile(id: TileId) {
    if (id === "all") {
      navigate("/");
      return;
    }
    if (id === "alert") navigate("/alerts");
    else if (id === "incident") navigate("/incidents");
    else if (id === "customers") navigate("/customers");
    else if (id === "event") navigate("/events");
    else if (id === "vulnerability") navigate("/vulnerabilities");
    else if (id === "patch_gap") navigate("/patch-gaps");
  }

  const isCommandCenter = location.pathname === "/" || location.pathname === "";

  return (
    <div className={`ops ops-fit ops-routed ${isCommandCenter ? "ops-cc" : ""}`}>
      {!isCommandCenter && (
        <header className="ops-top">
          <button type="button" className="brand brand-btn" onClick={() => navigate("/")}>
            SOC AGENT<span>CONSOLE</span>
          </button>
          <div className="meta">
            <span className="live-pill">
              <i />
              LIVE
            </span>
            <span>{user?.full_name || user?.email}</span>
            <span>·</span>
            <span>{user?.role}</span>
            <button type="button" className="btn btn-ghost" onClick={logout}>
              Sign out
            </button>
          </div>
        </header>
      )}

      {!isCommandCenter && <SocTiles kpis={kpis} active={active} onSelect={onSelectTile} />}

      <div className={`ops-outlet ${isCommandCenter ? "ops-outlet-cc" : ""}`}>
        <Outlet context={{ setKpis }} />
      </div>
    </div>
  );
}

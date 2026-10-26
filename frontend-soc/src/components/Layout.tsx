import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

export default function Layout() {
  const { user, logout } = useAuth();
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          SOC AGENT
          <span>Kevantic Console</span>
        </div>
        <nav className="nav">
          <NavLink to="/" end>
            Overview
          </NavLink>
          <NavLink to="/alerts">Alerts</NavLink>
          <NavLink to="/events">Events</NavLink>
          <NavLink to="/incidents">Incidents</NavLink>
          <NavLink to="/chat">AI Chat</NavLink>
        </nav>
        <button type="button" className="btn btn-ghost" style={{ color: "#fff", borderColor: "rgba(255,255,255,.35)" }} onClick={logout}>
          Sign out
        </button>
      </aside>
      <main className="main">
        <div className="topbar">
          <h1>Security Operations</h1>
          <div className="userchip">
            {user?.full_name || user?.email} · {user?.role}
          </div>
        </div>
        <Outlet />
      </main>
    </div>
  );
}

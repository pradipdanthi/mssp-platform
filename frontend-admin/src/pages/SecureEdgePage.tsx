import { useEffect, useState } from "react";
import {
  createSecureEdgeSite,
  getSecureEdgeEvents,
  getSecureEdgeNodes,
  getSecureEdgeSites,
  getSecureEdgeSummary,
  type SecureEdgeEvent,
  type SecureEdgeNode,
  type SecureEdgeSite,
  type SecureEdgeSummary,
} from "../api/admin";
import { ApiError } from "../api/client";

export default function SecureEdgePage() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<SecureEdgeSummary | null>(null);
  const [nodes, setNodes] = useState<SecureEdgeNode[]>([]);
  const [sites, setSites] = useState<SecureEdgeSite[]>([]);
  const [events, setEvents] = useState<SecureEdgeEvent[]>([]);
  const [host, setHost] = useState("");
  const [origin, setOrigin] = useState("");
  const [tenant, setTenant] = useState("");
  const [msg, setMsg] = useState<string | null>(null);

  function load() {
    setLoading(true);
    setError(null);
    Promise.all([
      getSecureEdgeSummary(),
      getSecureEdgeNodes(),
      getSecureEdgeSites(),
      getSecureEdgeEvents(40),
    ])
      .then(([sum, n, s, e]) => {
        setSummary(sum);
        setNodes(n.nodes || []);
        setSites(s.sites || []);
        setEvents(e.events || []);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load Secure Edge"))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load();
  }, []);

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    setMsg(null);
    try {
      await createSecureEdgeSite({
        tenant_short_code: tenant.trim(),
        public_hostname: host.trim(),
        origin_url: origin.trim(),
        tls_mode: "http_only",
      });
      setMsg("Site created — the customer’s dedicated Secure Edge will pull config within ~30s.");
      setHost("");
      setOrigin("");
      load();
    } catch (err) {
      setMsg(err instanceof ApiError ? err.message : "Create failed");
    }
  }

  if (loading) {
    return (
      <div className="page">
        <h1 className="page-title">Secure Edge</h1>
        <p className="muted">Loading…</p>
      </div>
    );
  }

  return (
    <div className="page">
      <h1 className="page-title">NikTiar™ Secure Edge</h1>
      <p className="muted">
        Dedicated <strong>NikTiar™ Secure Edge</strong> per customer — virtual{" "}
        <strong>HA pair</strong> by default, or <strong>physical 1U</strong> appliances when they have
        no virtual infra. Register sites here; configure NGFW / WAF / DNS Filter on the appliance
        console:{" "}
        <a href="http://192.168.0.217:9080/" target="_blank" rel="noreferrer">
          http://192.168.0.217:9080/
        </a>
      </p>
      <div className="card" style={{ padding: "1rem", marginBottom: "1rem", borderLeft: "4px solid #C8102E" }}>
        <strong>Operator guide</strong>
        <ol style={{ margin: "0.5rem 0 0 1.1rem", lineHeight: 1.5 }}>
          <li>Assign a dedicated edge (HA pair or physical) to the customer tenant.</li>
          <li>Create a site below (hostname → origin) for that tenant only.</li>
          <li>
            On the edge console, open <em>How this works</em>, then add NikTiar NGFW policies and URL
            / DNS Filter rules.
          </li>
          <li>Set NikTiar WAF Security Level (Medium is the safe default).</li>
          <li>Click <strong>Apply changes</strong> on the appliance so the edge reloads.</li>
        </ol>
      </div>
      {error && <p className="error-text">{error}</p>}

      <div className="kpi-row" style={{ display: "flex", gap: "1rem", flexWrap: "wrap", margin: "1rem 0" }}>
        <div className="card" style={{ padding: "1rem", minWidth: 140 }}>
          <div style={{ fontSize: "1.5rem", fontWeight: 700 }}>{nodes.length}</div>
          <div className="muted">Edge nodes</div>
        </div>
        <div className="card" style={{ padding: "1rem", minWidth: 140 }}>
          <div style={{ fontSize: "1.5rem", fontWeight: 700 }}>{summary?.enabled_sites ?? sites.length}</div>
          <div className="muted">Sites</div>
        </div>
        <div className="card" style={{ padding: "1rem", minWidth: 140 }}>
          <div style={{ fontSize: "1.5rem", fontWeight: 700 }}>{summary?.events_24h ?? 0}</div>
          <div className="muted">Events (24h)</div>
        </div>
      </div>

      <h2>Edge nodes</h2>
      <table className="data-table">
        <thead>
          <tr>
            <th>Hostname</th>
            <th>Mode</th>
            <th>Status</th>
            <th>Version</th>
            <th>Last heartbeat</th>
            <th>Config</th>
          </tr>
        </thead>
        <tbody>
          {nodes.map((n) => (
            <tr key={n.hostname}>
              <td>
                <code>{n.hostname}</code>
              </td>
              <td>{n.deployment_mode}</td>
              <td>{n.status}</td>
              <td>{n.version}</td>
              <td className="muted">{n.last_heartbeat_at || "—"}</td>
              <td>v{n.last_config_version}</td>
            </tr>
          ))}
          {!nodes.length && (
            <tr>
              <td colSpan={6} className="muted">
                No edge heartbeats yet
              </td>
            </tr>
          )}
        </tbody>
      </table>

      <h2 style={{ marginTop: "1.5rem" }}>Sites</h2>
      <table className="data-table">
        <thead>
          <tr>
            <th>Hostname</th>
            <th>Origin</th>
            <th>Tenant</th>
            <th>TLS</th>
            <th>Pin</th>
          </tr>
        </thead>
        <tbody>
          {sites.map((s) => (
            <tr key={s.id || s.public_hostname}>
              <td>
                <code>{s.public_hostname}</code>
              </td>
              <td className="muted">{s.origin_url}</td>
              <td>{s.tenant_short_code}</td>
              <td>{s.tls_mode}</td>
              <td className="muted">{s.edge_node_hostname || "Dedicated edge"}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <form onSubmit={onCreate} style={{ marginTop: "1rem", maxWidth: 720 }}>
        <h3>Add site (any tier add-on)</h3>
        <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
          <input
            placeholder="Tenant short code"
            value={tenant}
            onChange={(e) => setTenant(e.target.value)}
            required
          />
          <input
            placeholder="public.hostname"
            value={host}
            onChange={(e) => setHost(e.target.value)}
            required
          />
          <input
            placeholder="http://origin:8080"
            value={origin}
            onChange={(e) => setOrigin(e.target.value)}
            required
          />
          <button type="submit" className="btn btn-primary">
            Create
          </button>
        </div>
        {msg && <p className="muted">{msg}</p>}
      </form>

      <h2 style={{ marginTop: "1.5rem" }}>Recent events</h2>
      <table className="data-table">
        <thead>
          <tr>
            <th>When</th>
            <th>Type</th>
            <th>Severity</th>
            <th>Summary</th>
          </tr>
        </thead>
        <tbody>
          {events.map((ev) => (
            <tr key={String(ev.id)}>
              <td className="muted">{ev.created_at}</td>
              <td>{ev.event_type}</td>
              <td>{ev.severity}</td>
              <td>{ev.summary}</td>
            </tr>
          ))}
          {!events.length && (
            <tr>
              <td colSpan={4} className="muted">
                No events yet
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

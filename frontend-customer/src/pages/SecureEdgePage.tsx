import { useEffect, useState } from "react";
import {
  getCustomerEntitlements,
  getSecureEdgeSummary,
  type SecureEdgeCustomerSummary,
} from "../api/customer";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";

export default function SecureEdgePage() {
  const { user } = useAuth();
  const shortCode = user?.tenant_short_code ?? "";
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<SecureEdgeCustomerSummary | null>(null);

  useEffect(() => {
    if (!shortCode) {
      setLoading(false);
      setError("Tenant scope missing.");
      return;
    }
    setLoading(true);
    Promise.all([getCustomerEntitlements(shortCode), getSecureEdgeSummary(shortCode)])
      .then(([, sum]) => setData(sum))
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "Unable to load Secure Edge")
      )
      .finally(() => setLoading(false));
  }, [shortCode]);

  if (loading) {
    return (
      <div className="page">
        <h1 className="page-title">Secure Edge</h1>
        <p className="muted">Loading…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page">
        <h1 className="page-title">Secure Edge</h1>
        <p className="error-text">{error}</p>
      </div>
    );
  }

  if (!data?.enabled && !(data?.sites || []).length) {
    return (
      <div className="page">
        <h1 className="page-title">Secure Edge</h1>
        <p>
          Protect public web apps with NikTiar Secure Edge — next-gen firewall policies, URL filtering,
          and web application firewall in front of your sites. Available as an add-on on any tier — ask
          your SOC to enable sites for this tenant.
        </p>
      </div>
    );
  }

  return (
    <div className="page">
      <h1 className="page-title">Secure Edge</h1>
      <p className="muted">
        Your hostnames are terminated on NikTiar Secure Edge before traffic reaches your origin.
      </p>

      <div style={{ display: "flex", gap: "1rem", margin: "1rem 0" }}>
        <div className="card" style={{ padding: "1rem" }}>
          <div style={{ fontSize: "1.4rem", fontWeight: 700 }}>{data?.site_count ?? 0}</div>
          <div className="muted">Protected sites</div>
        </div>
        <div className="card" style={{ padding: "1rem" }}>
          <div style={{ fontSize: "1.4rem", fontWeight: 700 }}>{data?.event_count ?? 0}</div>
          <div className="muted">Recent edge events</div>
        </div>
      </div>

      <h2>Sites</h2>
      <table className="data-table">
        <thead>
          <tr>
            <th>Hostname</th>
            <th>TLS</th>
            <th>Status</th>
            <th>Edge</th>
          </tr>
        </thead>
        <tbody>
          {(data?.sites || []).map((s) => (
            <tr key={s.public_hostname}>
              <td>
                <code>{s.public_hostname}</code>
              </td>
              <td>{s.tls_mode}</td>
              <td>{s.enabled ? "Active" : "Disabled"}</td>
              <td className="muted">{s.edge_node_hostname || "Dedicated edge"}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2 style={{ marginTop: "1.25rem" }}>Recent blocks / events</h2>
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
          {(data?.events || []).map((ev, i) => (
            <tr key={`${ev.created_at}-${i}`}>
              <td className="muted">{ev.created_at}</td>
              <td>{ev.event_type}</td>
              <td>{ev.severity}</td>
              <td>{ev.summary}</td>
            </tr>
          ))}
          {!(data?.events || []).length && (
            <tr>
              <td colSpan={4} className="muted">
                No recent events
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

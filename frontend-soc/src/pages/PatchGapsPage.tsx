import { useEffect, useState } from "react";
import { Link, useOutletContext, useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { getPatchGaps, type PatchGapRow } from "../api/soc";
import Severity from "../components/Severity";
import { vulnerabilitiesListPath } from "../lib/socPaths";

type MonitorOutlet = {
  tenant?: { id: string; name: string; short_code: string } | null;
};

export default function PatchGapsPage() {
  const { logout } = useAuth();
  const { shortCode: routeShort } = useParams<{ shortCode?: string }>();
  const outlet = useOutletContext<MonitorOutlet | null>();
  const scopedShort = outlet?.tenant?.short_code || routeShort;
  const [rows, setRows] = useState<PatchGapRow[]>([]);
  const [total, setTotal] = useState(0);
  const [q, setQ] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    getPatchGaps({
      q: q.trim() || undefined,
      page_size: 100,
      short_code: scopedShort || undefined,
    })
      .then((r) => {
        setRows(r.items || []);
        setTotal(r.total || 0);
        setErr(null);
      })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) logout();
        else setErr("Failed to load patch gaps");
      })
      .finally(() => setLoading(false));
  }, [logout, q, scopedShort]);

  return (
    <div className="workbench">
      <div className="workbench-h">
        <div>
          <h2>Patch Gaps</h2>
          <p className="muted">
            Failed endpoint hardening / SCA checks (CIS and related). This is configuration drift — not the same as
            scanner CVEs under Vulnerabilities.
          </p>
        </div>
        <div className="workbench-filters">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search check / host / tenant"
            aria-label="Search patch gaps"
          />
          <Link className="btn btn-ghost" to={vulnerabilitiesListPath()}>
            Vulnerabilities (CVEs)
          </Link>
          {!scopedShort && (
            <Link className="btn btn-ghost" to="/">
              Back to feed
            </Link>
          )}
        </div>
      </div>
      <div className="workbench-b">
        {err && <div className="err">{err}</div>}
        <p className="muted" style={{ marginTop: 0 }}>
          {loading ? "Loading…" : `${total.toLocaleString()} failed checks`}
        </p>
        {!loading && rows.length === 0 ? (
          <div className="empty">No failed patch / hardening checks.</div>
        ) : (
          <table className="wb-table">
            <thead>
              <tr>
                <th>Severity</th>
                <th>Check</th>
                <th>Customer</th>
                <th>Host</th>
                <th>Policy</th>
                <th>Remediation</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td>
                    <Severity value={r.severity || "medium"} />
                  </td>
                  <td>
                    <div>{r.rule_title || r.check_id || "—"}</div>
                    <div className="muted" style={{ fontSize: "0.75rem" }}>
                      {r.check_id}
                    </div>
                  </td>
                  <td>
                    {r.short_code ? (
                      <Link to={`/monitor/${encodeURIComponent(r.short_code)}`}>{r.short_code}</Link>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td>{r.agent_name || "—"}</td>
                  <td>{r.policy_title || r.policy_id || "—"}</td>
                  <td style={{ maxWidth: 280 }}>{(r.remediation || r.rationale || "—").slice(0, 180)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

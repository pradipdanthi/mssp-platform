import { Link } from "react-router-dom";
import type { AlertTaxonomyCounts } from "../api/admin";

type Props = {
  counts: AlertTaxonomyCounts;
  activeCategory: string | null;
  severityFilter: string | null;
  statusFilter: string | null;
  tenantName: string;
};

function navLink(
  category: string | null,
  severityFilter: string | null,
  statusFilter: string | null
): string {
  const params = new URLSearchParams();
  if (category && category !== "all") params.set("category", category);
  if (severityFilter) params.set("severity", severityFilter);
  if (statusFilter) params.set("status", statusFilter);
  const q = params.toString();
  return q ? `/alerts?${q}` : "/alerts";
}

export default function AlertTaxonomyNav({
  counts,
  activeCategory,
  severityFilter,
  statusFilter,
  tenantName,
}: Props) {
  const active = activeCategory || "all";
  const customersHref = (() => {
    const params = new URLSearchParams();
    if (severityFilter) params.set("severity", severityFilter);
    if (statusFilter) params.set("status", statusFilter);
    const q = params.toString();
    return q ? `/alerts?${q}` : "/alerts";
  })();

  return (
    <nav className="alert-taxonomy-nav card-surface" aria-label="Alert device categories">
      <Link className="alert-taxonomy-back" to={customersHref}>
        ← All alerts
      </Link>
      <p className="alert-taxonomy-customer" title={tenantName}>
        {tenantName}
      </p>
      <h2 className="section-title" style={{ marginTop: "0.35rem", fontSize: "1rem" }}>
        Device taxonomy
      </h2>
      <ul className="alert-taxonomy-list">
        <li>
          <Link
            className={active === "all" ? "alert-taxonomy-link active" : "alert-taxonomy-link"}
            to={navLink(null, severityFilter, statusFilter)}
          >
            All Devices
            <span className="alert-taxonomy-badge">{counts.all ?? 0}</span>
          </Link>
        </li>
        <li>
          <Link
            className={
              active === "uncategorized" ? "alert-taxonomy-link active" : "alert-taxonomy-link"
            }
            to={navLink("uncategorized", severityFilter, statusFilter)}
          >
            Uncategorized
            <span className="alert-taxonomy-badge">{counts.uncategorized ?? 0}</span>
          </Link>
        </li>
      </ul>
      <p className="muted" style={{ fontSize: "0.85rem", margin: "0.5rem 0" }}>
        Endpoints &amp; workloads
      </p>
      <ul className="alert-taxonomy-list">
        {(
          [
            ["endpoints_windows", "Windows Systems"],
            ["endpoints_linux", "Linux & Unix"],
            ["endpoints_vm_container", "VMs & Containers"],
          ] as const
        ).map(([slug, label]) => (
          <li key={slug}>
            <Link
              className={active === slug ? "alert-taxonomy-link active" : "alert-taxonomy-link"}
              to={navLink(slug, severityFilter, statusFilter)}
            >
              {label}
              <span className="alert-taxonomy-badge">{counts[slug] ?? 0}</span>
            </Link>
          </li>
        ))}
      </ul>
      <p className="muted" style={{ fontSize: "0.85rem", margin: "0.5rem 0" }}>
        Network &amp; connectivity
      </p>
      <ul className="alert-taxonomy-list">
        {(
          [
            ["network_ids_sensors", "Network IDS / Sensors"],
            ["network_hardware", "Network Hardware"],
          ] as const
        ).map(([slug, label]) => (
          <li key={slug}>
            <Link
              className={active === slug ? "alert-taxonomy-link active" : "alert-taxonomy-link"}
              to={navLink(slug, severityFilter, statusFilter)}
            >
              {label}
              <span className="alert-taxonomy-badge">{counts[slug] ?? 0}</span>
            </Link>
          </li>
        ))}
      </ul>
      <p className="muted" style={{ fontSize: "0.85rem", margin: "0.5rem 0" }}>
        Security, data &amp; identity
      </p>
      <ul className="alert-taxonomy-list">
        {(
          [
            ["security_edge_appliances", "Firewalls / WAF / VPN"],
            ["databases_storage", "Databases & Storage"],
            ["identity_access", "Identity & Access"],
            ["iot_ot", "IoT / OT / Peripherals"],
          ] as const
        ).map(([slug, label]) => (
          <li key={slug}>
            <Link
              className={active === slug ? "alert-taxonomy-link active" : "alert-taxonomy-link"}
              to={navLink(slug, severityFilter, statusFilter)}
            >
              {label}
              <span className="alert-taxonomy-badge">{counts[slug] ?? 0}</span>
            </Link>
          </li>
        ))}
      </ul>
      <p className="muted" style={{ fontSize: "0.85rem", margin: "0.5rem 0" }}>
        Vulnerabilities &amp; posture
      </p>
      <ul className="alert-taxonomy-list">
        {(
          [
            ["vuln_web_app", "Web / API (Aegis)"],
            ["vuln_infrastructure", "Infrastructure CVE"],
          ] as const
        ).map(([slug, label]) => (
          <li key={slug}>
            <Link
              className={active === slug ? "alert-taxonomy-link active" : "alert-taxonomy-link"}
              to={navLink(slug, severityFilter, statusFilter)}
            >
              {label}
              <span className="alert-taxonomy-badge">{counts[slug] ?? 0}</span>
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}

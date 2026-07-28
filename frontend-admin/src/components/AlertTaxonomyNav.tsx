import { Link } from "react-router-dom";
import type { AlertTaxonomyCounts } from "../api/admin";

type Props = {
  counts: AlertTaxonomyCounts;
  activeCategory: string | null;
  severityFilter: string | null;
};

function navLink(
  category: string | null,
  _label: string,
  _count: number,
  severityFilter: string | null
): string {
  const params = new URLSearchParams();
  if (category && category !== "all") params.set("category", category);
  if (severityFilter) params.set("severity", severityFilter);
  const q = params.toString();
  return q ? `/alerts?${q}` : "/alerts";
}

export default function AlertTaxonomyNav({ counts, activeCategory, severityFilter }: Props) {
  const active = activeCategory || "all";

  return (
    <nav className="alert-taxonomy-nav card-surface" aria-label="Alert device categories">
      <h2 className="section-title" style={{ marginTop: 0, fontSize: "1rem" }}>
        Device taxonomy
      </h2>
      <ul className="alert-taxonomy-list">
        <li>
          <Link
            className={active === "all" ? "alert-taxonomy-link active" : "alert-taxonomy-link"}
            to={navLink(null, "All Devices", counts.all ?? 0, severityFilter)}
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
            to={navLink("uncategorized", "Uncategorized", counts.uncategorized ?? 0, severityFilter)}
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
              to={navLink(slug, label, counts[slug] ?? 0, severityFilter)}
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
              to={navLink(slug, label, counts[slug] ?? 0, severityFilter)}
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
              to={navLink(slug, label, counts[slug] ?? 0, severityFilter)}
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
            ["vuln_web_app", "Web / API (Nuclei)"],
            ["vuln_infrastructure", "Infrastructure CVE"],
          ] as const
        ).map(([slug, label]) => (
          <li key={slug}>
            <Link
              className={active === slug ? "alert-taxonomy-link active" : "alert-taxonomy-link"}
              to={navLink(slug, label, counts[slug] ?? 0, severityFilter)}
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

import { Link } from "react-router-dom";

export type StackModule = {
  id: string;
  name: string;
  blurb: string;
  status: "active" | "optional" | "requested";
};

type Props = {
  modules?: StackModule[];
  title?: string;
};

const DEFAULT_CUSTOMER: StackModule[] = [
  {
    id: "log_monitoring",
    name: "Log & event monitoring",
    blurb: "Included with your package",
    status: "active",
  },
  {
    id: "ir",
    name: "Incident Response",
    blurb: "Cases you can track in this portal",
    status: "active",
  },
  {
    id: "vuln",
    name: "Vulnerability Management",
    blurb: "See Vulnerabilities — entitlement controlled",
    status: "active",
  },
  {
    id: "nta",
    name: "Network Traffic Analysis",
    blurb: "Optional — ask your MSSP via subscription",
    status: "optional",
  },
  {
    id: "ti",
    name: "Threat Intelligence Sharing",
    blurb: "Optional — ask your MSSP via subscription",
    status: "optional",
  },
  {
    id: "edf",
    name: "Endpoint Forensics & Hunting",
    blurb: "Optional — ask your MSSP via subscription",
    status: "optional",
  },
];

/** Detection / service stack coverage — capability names only (no engine brands). */
export default function DetectionStackPanel({
  modules = DEFAULT_CUSTOMER,
  title = "Your subscribed services",
}: Props) {
  return (
    <section className="detection-stack card-surface" aria-label={title}>
      <div className="detection-stack-head">
        <h2 className="section-title" style={{ margin: 0 }}>
          {title}
        </h2>
        <p className="page-subtitle" style={{ margin: 0 }}>
          Services included in your package and optional add-ons. Browse the full catalog and request
          upgrades from <Link to="/services">Services</Link>.
        </p>
      </div>
      <div className="detection-stack-grid">
        {modules.map((m) => (
          <div key={m.id} className={"stack-tile stack-tile--" + m.status}>
            <div className="stack-tile-top">
              <span className="stack-tile-name">{m.name}</span>
              <span className={"stack-status stack-status--" + m.status}>
                {m.status === "active"
                  ? "Active"
                  : m.status === "requested"
                    ? "Requested"
                    : "Optional"}
              </span>
            </div>
            <div className="stack-tile-blurb">{m.blurb}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

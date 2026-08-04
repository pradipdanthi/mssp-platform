import { Link } from "react-router-dom";
import { catalogDisplayName, catalogShortHint } from "../data/serviceCatalog";

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

/** Keep in lockstep with Admin/Customer Service Catalog names. */
const DEFAULT_CUSTOMER: StackModule[] = [
  {
    id: "log_event_monitoring",
    name: catalogDisplayName("log_event_monitoring"),
    blurb: catalogShortHint("log_event_monitoring"),
    status: "active",
  },
  {
    id: "incident_response",
    name: catalogDisplayName("incident_response"),
    blurb: catalogShortHint("incident_response"),
    status: "active",
  },
  {
    id: "security_automation",
    name: catalogDisplayName("security_automation"),
    blurb: catalogShortHint("security_automation"),
    status: "active",
  },
  {
    id: "vulnerability_management",
    name: catalogDisplayName("vulnerability_management"),
    blurb: catalogShortHint("vulnerability_management"),
    status: "optional",
  },
  {
    id: "continuous_compliance",
    name: catalogDisplayName("continuous_compliance"),
    blurb: catalogShortHint("continuous_compliance"),
    status: "optional",
  },
  {
    id: "network_detection_response",
    name: catalogDisplayName("network_detection_response"),
    blurb: catalogShortHint("network_detection_response"),
    status: "optional",
  },
  {
    id: "threat_intelligence",
    name: catalogDisplayName("threat_intelligence"),
    blurb: catalogShortHint("threat_intelligence"),
    status: "optional",
  },
  {
    id: "endpoint_forensics_deception",
    name: catalogDisplayName("endpoint_forensics_deception"),
    blurb: catalogShortHint("endpoint_forensics_deception"),
    status: "optional",
  },
  {
    id: "external_attack_surface",
    name: catalogDisplayName("external_attack_surface"),
    blurb: catalogShortHint("external_attack_surface"),
    status: "optional",
  },
  {
    id: "cloud_identity_protection",
    name: catalogDisplayName("cloud_identity_protection"),
    blurb: catalogShortHint("cloud_identity_protection"),
    status: "optional",
  },
];

/** Detection / service stack coverage — capability names only (no engine brands). */
export default function DetectionStackPanel({
  modules = DEFAULT_CUSTOMER,
  title = "Service stack coverage",
}: Props) {
  return (
    <section className="detection-stack card-surface" aria-label={title}>
      <div className="detection-stack-head">
        <h2 className="section-title" style={{ margin: 0 }}>
          {title}
        </h2>
        <p className="page-subtitle" style={{ margin: 0 }}>
          Same names as your Service Portfolio. Optional modules activate when your MSSP enables
          them or after an approved request.
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
      <p className="page-subtitle" style={{ marginTop: "0.85rem" }}>
        <Link to="/services">Open Service Portfolio →</Link>
        {" · "}
        <Link to="/threatlens">Open ThreatLens →</Link>
      </p>
    </section>
  );
}

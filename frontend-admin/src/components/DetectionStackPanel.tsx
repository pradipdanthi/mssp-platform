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

const DEFAULT_ADMIN: StackModule[] = [
  {
    id: "siem",
    name: "SIEM & Log Management",
    blurb: "Central detection & retention",
    status: "active",
  },
  {
    id: "ir",
    name: "Incident Response",
    blurb: "Casework & investigation",
    status: "active",
  },
  {
    id: "soar",
    name: "Security Automation",
    blurb: "Playbook-driven response",
    status: "active",
  },
  {
    id: "vuln",
    name: "Vulnerability Management",
    blurb: "CVE discovery & guidance",
    status: "active",
  },
  {
    id: "nta",
    name: "Network Traffic Analysis",
    blurb: "Optional — enable via customer subscription",
    status: "optional",
  },
  {
    id: "ti",
    name: "Threat Intelligence Sharing",
    blurb: "Optional — enable via customer subscription",
    status: "optional",
  },
  {
    id: "edf",
    name: "Endpoint Forensics & Hunting",
    blurb: "Optional — enable via customer subscription",
    status: "optional",
  },
];

/** Detection / service stack coverage — capability names only (no engine brands). */
export default function DetectionStackPanel({
  modules = DEFAULT_ADMIN,
  title = "Service stack coverage",
}: Props) {
  return (
    <section className="detection-stack card-surface" aria-label={title}>
      <div className="detection-stack-head">
        <h2 className="section-title" style={{ margin: 0 }}>
          {title}
        </h2>
        <p className="page-subtitle" style={{ margin: 0 }}>
          Active services and optional add-ons. Optional modules activate from subscription
          entitlements and platform capacity.
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

import type { StackNode } from "../api/soc";

const LAYER_ORDER = ["frontend", "core", "engine", "ai", "edge", "ops"];
const LAYER_TITLE: Record<string, string> = {
  frontend: "Frontends",
  core: "Control plane",
  engine: "Detection engines",
  ai: "AI / SOC Agent",
  edge: "Customer edge",
  ops: "Notifications",
};

export default function StackSkeleton({
  nodes,
  generatedAt,
}: {
  nodes: StackNode[];
  generatedAt?: string | null;
}) {
  const byLayer = LAYER_ORDER.map((layer) => ({
    layer,
    title: LAYER_TITLE[layer] || layer,
    nodes: nodes.filter((n) => n.layer === layer),
  })).filter((g) => g.nodes.length > 0);

  return (
    <section className="stack-skel" aria-label="MSSP system skeleton">
      <div className="stack-head">
        <h2>
          System skeleton <span className="live-pill"><i />Live pulse</span>
        </h2>
        <span className="muted">
          DNS of the whole MSSP stack · portals · API · engines · appliances
          {generatedAt ? ` · synced ${new Date(generatedAt).toLocaleTimeString()}` : ""}
        </span>
      </div>
      <div className="stack-flow">
        {byLayer.map((g, idx) => (
          <div key={g.layer} className="stack-layer-wrap">
            {idx > 0 && <div className="stack-pipe" aria-hidden="true" />}
            <div className="stack-layer">
              <div className="stack-layer-title">{g.title}</div>
              <div className="stack-nodes">
                {g.nodes.map((n) => (
                  <div
                    key={n.id}
                    className={`stack-node st-${n.status || "unknown"} ${n.pulse > 0 ? "pulsing" : ""}`}
                    title={n.detail}
                  >
                    <div className="sn-top">
                      <span className="sn-dot" />
                      <span className="sn-label">{n.label}</span>
                    </div>
                    <div className="sn-metric">{n.metric || n.status}</div>
                    <div className="sn-detail">{n.detail}</div>
                    {n.pulse > 0 && <div className="sn-pulse">pulse {n.pulse}</div>}
                  </div>
                ))}
              </div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

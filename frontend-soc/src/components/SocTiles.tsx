export type SocKpis = {
  alerts?: number;
  incidents?: number;
  events?: number;
  vulnerabilities?: number;
  patch_gaps?: number;
  customers?: number;
};

export type TileId =
  | "all"
  | "alert"
  | "incident"
  | "event"
  | "vulnerability"
  | "patch_gap"
  | "customers";

const TILES: {
  id: TileId;
  label: string;
  key: keyof SocKpis;
  tone: string;
}[] = [
  { id: "alert", label: "Security Alerts", key: "alerts", tone: "tone-red" },
  { id: "incident", label: "Incidents", key: "incidents", tone: "tone-amber" },
  { id: "event", label: "Events", key: "events", tone: "tone-blue" },
  { id: "vulnerability", label: "Vulnerabilities", key: "vulnerabilities", tone: "tone-purple" },
  { id: "patch_gap", label: "Patch Gaps", key: "patch_gaps", tone: "tone-green" },
  { id: "customers", label: "Customers", key: "customers", tone: "tone-cyan" },
];

export default function SocTiles({
  kpis,
  active,
  onSelect,
}: {
  kpis?: SocKpis | null;
  active: TileId;
  onSelect: (t: TileId) => void;
}) {
  const data = kpis || {};
  return (
    <section className="soc-tiles soc-tiles-6" aria-label="SOC focus tiles">
      {TILES.map((t) => (
        <button
          key={t.id}
          type="button"
          className={`soc-tile ${t.tone} ${active === t.id ? "is-active" : ""}`}
          onClick={() => onSelect(active === t.id && active !== "all" ? "all" : t.id)}
          title={`Open ${t.label}`}
        >
          <div className="soc-tile-label">{t.label}</div>
          <div className="soc-tile-value">{Number(data[t.key] ?? 0).toLocaleString()}</div>
        </button>
      ))}
    </section>
  );
}

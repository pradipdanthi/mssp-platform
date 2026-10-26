import type { StackSkeleton } from "../api/soc";

const TILES: { key: keyof NonNullable<StackSkeleton["kpis"]>; label: string; hint: string; tone: string }[] = [
  { key: "alerts_1h", label: "Alerts / 1h", hint: "Ingest velocity", tone: "tone-red" },
  { key: "high_open", label: "High open", hint: "Critical + high", tone: "tone-red" },
  { key: "open_incidents", label: "Incidents", hint: "Open cases", tone: "tone-amber" },
  { key: "edge_24h", label: "Edge / 24h", hint: "Secure Edge", tone: "tone-amber" },
  { key: "appliances_online", label: "Appliances", hint: "Online now", tone: "tone-green" },
  { key: "ai_triaged_24h", label: "AI triage / 24h", hint: "SOC Agent", tone: "tone-purple" },
  { key: "heartbeats_15m", label: "Heartbeats", hint: "Last 15 min", tone: "tone-blue" },
  { key: "active_tenants", label: "Tenants", hint: "Active", tone: "tone-blue" },
];

export default function KpiTiles({ kpis }: { kpis?: StackSkeleton["kpis"] | null }) {
  const data = kpis || {};
  return (
    <section className="kpi-row" aria-label="MSSP pulse tiles">
      {TILES.map((t) => (
        <article key={t.key} className={`kpi-tile ${t.tone}`}>
          <div className="kpi-label">{t.label}</div>
          <div className="kpi-value">{Number(data[t.key] ?? 0).toLocaleString()}</div>
          <div className="kpi-hint">{t.hint}</div>
        </article>
      ))}
    </section>
  );
}

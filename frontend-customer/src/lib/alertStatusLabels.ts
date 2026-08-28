/** UI-only alert status labels. DB / API values stay unchanged. */
const ALERT_STATUS_LABELS: Record<string, string> = {
  new: "Open",
  triaged: "In Review",
  incident_created: "Incident created",
  false_positive: "False positive",
  closed: "Closed",
};

export function alertStatusLabel(status: string | null | undefined): string {
  const raw = (status || "").trim();
  if (!raw) return "—";
  const key = raw.toLowerCase();
  return ALERT_STATUS_LABELS[key] ?? raw.replace(/_/g, " ");
}

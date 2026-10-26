/** UI-only status labels. DB values stay unchanged. */

const ALERT_STATUS_LABELS: Record<string, string> = {
  new: "Open",
  triaged: "In Review",
  incident_created: "Incident created",
  false_positive: "False Positive",
  closed: "Closed",
};

const INCIDENT_STATUS_LABELS: Record<string, string> = {
  open: "Open",
  in_progress: "In progress",
  waiting_customer: "Waiting customer",
  resolved: "Resolved",
  closed: "Closed",
};

export function alertStatusLabel(status: string): string {
  const key = (status || "").toLowerCase().trim();
  return ALERT_STATUS_LABELS[key] ?? status;
}

export function incidentStatusLabel(status: string): string {
  const key = (status || "").toLowerCase().trim();
  return INCIDENT_STATUS_LABELS[key] ?? status;
}

export function statusDisplayLabel(status: string, kind: "alert" | "incident" = "alert"): string {
  return kind === "incident" ? incidentStatusLabel(status) : alertStatusLabel(status);
}

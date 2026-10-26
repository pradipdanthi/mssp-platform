/** Path helpers — keep drill-down inside /monitor/:shortCode when on a customer wall. */

function monitorShortCode(): string | null {
  if (typeof window === "undefined") return null;
  const m = window.location.pathname.match(/^\/monitor\/([^/]+)/i);
  return m ? decodeURIComponent(m[1]) : null;
}

export function alertsListPath(): string {
  const code = monitorShortCode();
  return code ? `/monitor/${encodeURIComponent(code)}/alerts` : "/alerts";
}

export function alertDetailPath(alertId: string): string {
  const code = monitorShortCode();
  return code
    ? `/monitor/${encodeURIComponent(code)}/alerts/${encodeURIComponent(alertId)}`
    : `/alerts/${encodeURIComponent(alertId)}`;
}

export function incidentsListPath(): string {
  const code = monitorShortCode();
  return code ? `/monitor/${encodeURIComponent(code)}/incidents` : "/incidents";
}

export function incidentDetailPath(incidentId: string): string {
  const code = monitorShortCode();
  return code
    ? `/monitor/${encodeURIComponent(code)}/incidents/${encodeURIComponent(incidentId)}`
    : `/incidents/${encodeURIComponent(incidentId)}`;
}

export function vulnerabilitiesListPath(): string {
  const code = monitorShortCode();
  return code ? `/monitor/${encodeURIComponent(code)}/vulnerabilities` : "/vulnerabilities";
}

export function patchGapsListPath(): string {
  const code = monitorShortCode();
  return code ? `/monitor/${encodeURIComponent(code)}/patch-gaps` : "/patch-gaps";
}

/**
 * VirusTotal enrichment helpers for AI SOC Assist.
 * Types/formats VT stats from the triage API response — never calls VT directly
 * and never handles VT_API_KEY (server-side only).
 */

export type VtEnrichmentStatus =
  | "ok"
  | "not_configured"
  | "no_hash"
  | "not_found"
  | "timeout"
  | "rate_limited"
  | "error"
  | string;

export type VtEnrichmentStats = {
  status: VtEnrichmentStatus;
  hash?: string;
  malicious?: number;
  suspicious?: number;
  harmless?: number;
  undetected?: number;
  message?: string;
  http_status?: number;
};

export type VtChip = {
  id: string;
  label: string;
  tone: "neutral" | "ok" | "warn" | "bad" | "muted";
};

/** Pull VT block from triage enrichment / top-level vt field. */
export function extractVtStats(triage: {
  vt?: unknown;
  enrichment?: { threat_intel?: { external_vt?: unknown } } | null;
  context_summary?: {
    vt_status?: string;
    vt_malicious?: number | null;
    vt_suspicious?: number | null;
    vt_harmless?: number | null;
    vt_undetected?: number | null;
  } | null;
}): VtEnrichmentStats | null {
  const fromTop = triage.vt;
  const fromEnrich =
    triage.enrichment &&
    typeof triage.enrichment === "object" &&
    (triage.enrichment as { threat_intel?: { external_vt?: unknown } }).threat_intel
      ?.external_vt;
  const raw = fromTop ?? fromEnrich;
  if (raw && typeof raw === "object" && !Array.isArray(raw)) {
    const o = raw as Record<string, unknown>;
    return {
      status: String(o.status || "unknown"),
      hash: o.hash != null ? String(o.hash) : undefined,
      malicious: numOrUndef(o.malicious),
      suspicious: numOrUndef(o.suspicious),
      harmless: numOrUndef(o.harmless),
      undetected: numOrUndef(o.undetected),
      message: o.message != null ? String(o.message) : undefined,
      http_status: numOrUndef(o.http_status),
    };
  }
  // Fallback: context_summary VT fields
  const summary = triage.context_summary;
  if (summary?.vt_status) {
    return {
      status: summary.vt_status,
      malicious: summary.vt_malicious ?? undefined,
      suspicious: summary.vt_suspicious ?? undefined,
      harmless: summary.vt_harmless ?? undefined,
      undetected: summary.vt_undetected ?? undefined,
    };
  }
  return null;
}

function numOrUndef(v: unknown): number | undefined {
  if (v == null || v === "") return undefined;
  const n = Number(v);
  return Number.isFinite(n) ? n : undefined;
}

/** Chips for the Context used strip. */
export function formatVtChips(vt: VtEnrichmentStats | null | undefined): VtChip[] {
  if (!vt) return [];
  const status = (vt.status || "").toLowerCase();
  if (status === "not_configured") {
    return [{ id: "vt-status", label: "VT not configured", tone: "muted" }];
  }
  if (status === "no_hash") {
    return [{ id: "vt-status", label: "VT no hash", tone: "muted" }];
  }
  if (status === "not_found") {
    return [{ id: "vt-status", label: "VT not found", tone: "neutral" }];
  }
  if (status === "timeout") {
    return [{ id: "vt-status", label: "VT timeout", tone: "warn" }];
  }
  if (status === "rate_limited") {
    return [{ id: "vt-status", label: "VT rate limited", tone: "warn" }];
  }
  if (status === "error") {
    return [{ id: "vt-status", label: "VT error", tone: "warn" }];
  }
  if (status !== "ok") {
    return [{ id: "vt-status", label: `VT ${status}`, tone: "muted" }];
  }
  const mal = vt.malicious ?? 0;
  const sus = vt.suspicious ?? 0;
  const harm = vt.harmless ?? 0;
  const und = vt.undetected ?? 0;
  const chips: VtChip[] = [
    {
      id: "vt-mal",
      label: `VT mal ${mal}`,
      tone: mal > 0 ? "bad" : "ok",
    },
    {
      id: "vt-sus",
      label: `sus ${sus}`,
      tone: sus >= 3 ? "warn" : sus > 0 ? "warn" : "neutral",
    },
    {
      id: "vt-harm",
      label: `harmless ${harm}`,
      tone: "neutral",
    },
    {
      id: "vt-und",
      label: `undet ${und}`,
      tone: "muted",
    },
  ];
  return chips;
}

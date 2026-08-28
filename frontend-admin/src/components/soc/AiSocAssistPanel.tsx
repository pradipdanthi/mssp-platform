import { useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import {
  actionLabel,
  AiSuggestedSuppressionScope,
  AiTriageContextSummary,
  AiTriageResult,
  fetchAdminAiTriage,
  riskHintLabel,
  verdictBadgeClass,
  verdictLabel,
} from "../../lib/ai-triage";
import { extractVtStats, formatVtChips } from "../../lib/services/vt-enrichment";

type Props = {
  alertId: string;
  /** When true, show Apply AI Recommendation & Suppress */
  canSuppress: boolean;
  onApplySuppress: (scope: AiSuggestedSuppressionScope) => void;
};

function contextStrip(
  summary: AiTriageContextSummary | null | undefined,
  triage: AiTriageResult | null
) {
  if (!summary && !triage) return null;
  const device = summary?.device_type || "unknown";
  const ti = summary?.ti_hit ? "Y" : "N";
  const related = summary?.related_alerts_count ?? 0;
  const priorFp = summary?.prior_fp_count ?? 0;
  const sameRule = summary?.prior_fp_same_rule ?? 0;
  const sameProc = summary?.prior_fp_same_process ?? 0;
  const supp = summary?.suppression_match ? "Y" : "N";
  const vtChips = formatVtChips(extractVtStats(triage || {}));
  return (
    <p className="ai-context-strip" aria-label="Context used">
      <span className="ai-context-label">Context used:</span>
      <span>Device {device}</span>
      <span className="ai-context-sep">·</span>
      <span>TI hit {ti}</span>
      <span className="ai-context-sep">·</span>
      <span>Related {related}</span>
      <span className="ai-context-sep">·</span>
      <span>Prior FP {priorFp}</span>
      {sameRule > 0 ? (
        <>
          <span className="ai-context-sep">·</span>
          <span>Same rule FP {sameRule}</span>
        </>
      ) : null}
      {sameProc > 0 ? (
        <>
          <span className="ai-context-sep">·</span>
          <span>Same process FP {sameProc}</span>
        </>
      ) : null}
      <span className="ai-context-sep">·</span>
      <span>Suppression {supp}</span>
      {summary?.signature_status ? (
        <>
          <span className="ai-context-sep">·</span>
          <span>Sig {summary.signature_status}</span>
        </>
      ) : null}
      {vtChips.map((chip) => (
        <span key={chip.id}>
          <span className="ai-context-sep">·</span>
          <span className={`ai-vt-chip ai-vt-chip--${chip.tone}`}>{chip.label}</span>
        </span>
      ))}
    </p>
  );
}

function riskHintsStrip(triage: AiTriageResult) {
  const flags =
    triage.pre_score_hints?.flags ||
    triage.context_summary?.pre_score_flags ||
    triage.enrichment?.pre_score_hints?.flags ||
    [];
  if (!flags.length) return null;
  return (
    <p className="ai-risk-hints" aria-label="Risk hints">
      <span className="ai-context-label">Risk hints:</span>
      {flags.map((flag) => (
        <span key={flag} className="ai-risk-chip">
          {riskHintLabel(flag)}
        </span>
      ))}
    </p>
  );
}

/**
 * On-demand Tier-1 AI SOC Assist panel for alert detail (never on list load).
 */
export default function AiSocAssistPanel({ alertId, canSuppress, onApplySuppress }: Props) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [triage, setTriage] = useState<AiTriageResult | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setTriage(null);
    fetchAdminAiTriage(alertId)
      .then((res) => {
        if (!cancelled) setTriage(res.triage);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(
          err instanceof ApiError && typeof err.detail === "string"
            ? err.detail
            : "AI triage unavailable (timeout or model error)."
        );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [alertId]);

  const summary =
    triage?.context_summary || triage?.enrichment?.context_summary || null;
  const queueSuggestion =
    triage?.ai_queue ||
    triage?.queue_suggestion ||
    summary?.queue_suggestion ||
    null;

  return (
    <section className="ai-soc-assist" aria-label="AI SOC Assist">
      <h2 className="section-title">AI SOC Assist</h2>
      {loading ? <p className="page-subtitle">Running Tier-1 triage…</p> : null}
      {error ? <div className="state-message state-error">{error}</div> : null}
      {triage ? (
        <div className="ai-soc-assist-body">
          {queueSuggestion === "low_priority" ||
          queueSuggestion === "ROUTE_LOW_PRIORITY" ? (
            <div className="ai-queue-banner" role="status">
              Suggest low-priority review — BENIGN_FALSE_POSITIVE with confidence ≥ 85%.
              {triage.auto_close?.auto_closed
                ? " Auto-closed (ENABLE_AUTO_CLOSE_LOW_RISK)."
                : " Alert is not auto-closed unless the opt-in flag is enabled."}
            </div>
          ) : null}
          <div className="ai-soc-assist-header">
            <span className={verdictBadgeClass(triage.verdict)}>
              {verdictLabel(triage.verdict)}
            </span>
            <span className="ai-confidence">
              {Math.round(triage.confidence)}% Confidence
            </span>
            {triage.cached ? <span className="ai-cache-pill">Cached</span> : null}
            {triage.auto_close?.auto_closed ? (
              <span className="ai-triaged-chip" title="Closed by opt-in AI auto-triage">
                AI Triaged
              </span>
            ) : null}
          </div>
          {contextStrip(summary, triage)}
          {riskHintsStrip(triage)}
          <p className="ai-summary">{triage.summary}</p>
          <p className="ai-action">
            <strong>Recommended action:</strong> {actionLabel(triage.recommended_action)}
          </p>
          {triage.action_rationale ? (
            <p className="ai-action-rationale">{triage.action_rationale}</p>
          ) : null}
          {canSuppress ? (
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => onApplySuppress(triage.suggested_suppression_scope)}
            >
              Apply AI Recommendation &amp; Suppress
            </button>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

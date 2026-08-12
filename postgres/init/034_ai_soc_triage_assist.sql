-- KB-096 Phase 1: AI SOC Triage Assist columns (additive only).
-- Complements Threat Intel — does not replace IOC tables.
-- Draft fields for human SOC finalize; never auto customer_visible.

ALTER TABLE security_alerts
  ADD COLUMN IF NOT EXISTS ai_risk_score NUMERIC(5,2),
  ADD COLUMN IF NOT EXISTS ai_risk_rationale TEXT,
  ADD COLUMN IF NOT EXISTS ai_enrichment_notes TEXT,
  ADD COLUMN IF NOT EXISTS ai_correlation_notes TEXT,
  ADD COLUMN IF NOT EXISTS ai_containment_suggestion TEXT,
  ADD COLUMN IF NOT EXISTS ai_triage_status TEXT,
  ADD COLUMN IF NOT EXISTS ai_triaged_at TIMESTAMPTZ;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'security_alerts_ai_triage_status_check'
  ) THEN
    ALTER TABLE security_alerts
      ADD CONSTRAINT security_alerts_ai_triage_status_check
      CHECK (
        ai_triage_status IS NULL
        OR ai_triage_status IN ('draft', 'accepted', 'rejected', 'stale')
      );
  END IF;
END $$;

COMMENT ON COLUMN security_alerts.ai_risk_score IS
  'KB-096 AI SOC draft risk 0-100; human SOC finalizes.';
COMMENT ON COLUMN security_alerts.ai_enrichment_notes IS
  'KB-096 AI notes citing Threat Intel IOC matches (complement, not replace TI).';
COMMENT ON COLUMN security_alerts.ai_correlation_notes IS
  'KB-096 AI notes on related alerts/incidents for analyst.';
COMMENT ON COLUMN security_alerts.ai_containment_suggestion IS
  'KB-096 AI draft containment suggestion for human SOC decision only; never auto-executed.';

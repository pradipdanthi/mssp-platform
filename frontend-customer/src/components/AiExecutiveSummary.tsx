/**
 * Card 2 — AI Executive Summary (plain English, 3 bullets).
 * Uses existing customer-safe incident fields only.
 */
export default function AiExecutiveSummary({
  whatHappened,
  businessImpact,
  actionTaken,
}: {
  whatHappened?: string | null;
  businessImpact?: string | null;
  actionTaken?: string | null;
}) {
  const what = (whatHappened || "").trim() || "Summary is being prepared by your SOC.";
  const impact =
    (businessImpact || "").trim() || "Business impact assessment is pending analyst review.";
  const action =
    (actionTaken || "").trim() ||
    "No customer action recorded yet — your MSSP is managing the case.";

  return (
    <section className="card-surface ai-exec-summary" aria-label="AI executive summary">
      <div className="ai-exec-kicker">AI Executive Summary</div>
      <h2 className="page-subtitle" style={{ marginTop: "0.35rem" }}>
        What leaders need to know
      </h2>
      <ol className="ai-exec-list">
        <li>
          <strong>What happened</strong>
          <p>{what}</p>
        </li>
        <li>
          <strong>Business impact</strong>
          <p>{impact}</p>
        </li>
        <li>
          <strong>Action Taken by Junexis SOC</strong>
          <p>{action}</p>
        </li>
      </ol>
    </section>
  );
}

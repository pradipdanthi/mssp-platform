export default function AlertsPage() {
  return (
    <div>
      <h1 className="page-title">Alerts</h1>
      <p className="page-subtitle">Customer-visible alert summaries for your organization.</p>
      <div className="state-message">
        A dedicated customer alerts API is planned for a future module. This customer portal does
        not call admin alert endpoints. Until that API exists, alert visibility is limited to
        incident and recommendation summaries on the Dashboard.
      </div>
    </div>
  );
}

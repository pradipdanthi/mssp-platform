import { Link } from "react-router-dom";
import { getCustomerRecommendations } from "../api/customer";
import { useAuth } from "../auth/AuthContext";
import { useCustomerQuery } from "../hooks/useCustomerQuery";

export default function RecommendationsPage() {
  const { user } = useAuth();
  const shortCode = user?.tenant_short_code ?? null;
  const { status, data, errorMessage } = useCustomerQuery(
    () => getCustomerRecommendations(shortCode as string),
    Boolean(shortCode),
    [shortCode]
  );

  if (!shortCode) {
    return (
      <div>
        <h1 className="page-title">Recommendations</h1>
        <div className="state-message state-error">
          This account is not linked to a customer tenant, so recommendations cannot be loaded.
        </div>
      </div>
    );
  }

  return (
    <div>
      <h1 className="page-title">Recommendations</h1>
      <p className="page-subtitle">
        Read-only customer-visible security recommendations for your organization, including open
        and historical items.
      </p>

      {status === "loading" && <div className="state-message">Loading recommendations...</div>}
      {status === "forbidden" && (
        <div className="state-message state-error">Access denied for this customer portal view.</div>
      )}
      {(status === "error" || status === "not_found") && (
        <div className="state-message state-error">{errorMessage}</div>
      )}

      {status === "success" && data && (
        data.recommendations.length === 0 ? (
          <div className="state-message">
            No customer-visible recommendations right now. Your SOC team may still be preparing
            items that are not yet shared with your organization.
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Priority</th>
                <th>Status</th>
                <th>Category</th>
                <th>Description</th>
                <th>Due</th>
                <th>Completed</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {data.recommendations.map((rec) => (
                <tr key={rec.recommendation_id}>
                  <td>
                    <Link to={`/recommendations/${encodeURIComponent(rec.recommendation_id)}`}>
                      {rec.title}
                    </Link>
                  </td>
                  <td>
                    <span className={`badge badge-${rec.priority}`}>{rec.priority}</span>
                  </td>
                  <td>{rec.status}</td>
                  <td>{rec.category}</td>
                  <td>{rec.description}</td>
                  <td>{rec.due_at ?? "—"}</td>
                  <td>{rec.completed_at ?? "—"}</td>
                  <td>{rec.created_at ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      )}
    </div>
  );
}

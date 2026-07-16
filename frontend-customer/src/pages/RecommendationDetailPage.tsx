import { Link, useParams } from "react-router-dom";
import { getCustomerRecommendationDetail } from "../api/customer";
import { useAuth } from "../auth/AuthContext";
import { useCustomerQuery } from "../hooks/useCustomerQuery";

export default function RecommendationDetailPage() {
  const { user } = useAuth();
  const { recommendationId } = useParams<{ recommendationId: string }>();
  const shortCode = user?.tenant_short_code ?? null;
  const { status, data, errorMessage } = useCustomerQuery(
    () => getCustomerRecommendationDetail(shortCode as string, recommendationId as string),
    Boolean(shortCode && recommendationId),
    [shortCode, recommendationId]
  );

  if (!shortCode) {
    return (
      <div>
        <h1 className="page-title">Recommendation</h1>
        <div className="state-message state-error">
          This account is not linked to a customer tenant, so recommendation detail cannot be loaded.
        </div>
      </div>
    );
  }

  if (!recommendationId) {
    return (
      <div>
        <h1 className="page-title">Recommendation</h1>
        <div className="state-message state-error">Recommendation id is missing from the URL.</div>
        <p>
          <Link to="/recommendations">Back to recommendations</Link>
        </p>
      </div>
    );
  }

  return (
    <div>
      <p>
        <Link to="/recommendations">← Back to recommendations</Link>
      </p>
      <h1 className="page-title">Recommendation</h1>
      <p className="page-subtitle">Read-only customer-visible detail for this recommendation.</p>

      {status === "loading" && <div className="state-message">Loading recommendation...</div>}
      {status === "forbidden" && (
        <div className="state-message state-error">Access denied for this customer portal view.</div>
      )}
      {(status === "error" || status === "not_found") && (
        <div className="state-message state-error">{errorMessage ?? "Recommendation was not found."}</div>
      )}

      {status === "success" && data && (
        <table className="data-table">
          <tbody>
            <tr>
              <th>Title</th>
              <td>{data.recommendation.title}</td>
            </tr>
            <tr>
              <th>Priority</th>
              <td>
                <span className={`badge badge-${data.recommendation.priority}`}>
                  {data.recommendation.priority}
                </span>
              </td>
            </tr>
            <tr>
              <th>Status</th>
              <td>{data.recommendation.status}</td>
            </tr>
            <tr>
              <th>Category</th>
              <td>{data.recommendation.category}</td>
            </tr>
            <tr>
              <th>Description</th>
              <td>{data.recommendation.description}</td>
            </tr>
            <tr>
              <th>Due</th>
              <td>{data.recommendation.due_at ?? "—"}</td>
            </tr>
            <tr>
              <th>Completed</th>
              <td>{data.recommendation.completed_at ?? "—"}</td>
            </tr>
            <tr>
              <th>Created</th>
              <td>{data.recommendation.created_at ?? "—"}</td>
            </tr>
            <tr>
              <th>Updated</th>
              <td>{data.recommendation.updated_at ?? "—"}</td>
            </tr>
          </tbody>
        </table>
      )}
    </div>
  );
}

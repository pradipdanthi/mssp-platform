import { getUsers } from "../api/admin";
import { useAdminQuery } from "../hooks/useAdminQuery";

export default function UsersPage() {
  const { status, data, errorMessage } = useAdminQuery(() => getUsers(), []);

  return (
    <div>
      <h1 className="page-title">Users</h1>
      <p className="page-subtitle">
        Read-only view. User create/edit and password reset are planned for a future module.
      </p>

      {status === "loading" && <div className="state-message">Loading users...</div>}
      {status === "forbidden" && (
        <div className="state-message state-error">
          Access denied. Your account does not have permission to view users.
        </div>
      )}
      {status === "error" && <div className="state-message state-error">{errorMessage}</div>}

      {status === "success" && data && (
        data.users.length === 0 ? (
          <div className="state-message">No users yet.</div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Email</th>
                <th>Role</th>
                <th>Type</th>
                <th>Status</th>
                <th>Last Login</th>
              </tr>
            </thead>
            <tbody>
              {/* AdminUser has no password/password_hash field, so there is
                  nothing here that could ever render one. */}
              {data.users.map((u) => (
                <tr key={u.id}>
                  <td>{u.full_name}</td>
                  <td>{u.email}</td>
                  <td>{u.role}</td>
                  <td>{u.user_type}</td>
                  <td>
                    <span className={`badge badge-${u.status}`}>{u.status}</span>
                  </td>
                  <td>{u.last_login_at ?? "Never"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      )}
    </div>
  );
}

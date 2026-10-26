import { FormEvent, useState } from "react";
import { Navigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";

export default function LoginPage() {
  const { token, login, completeMfa, error, clearError } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mfaToken, setMfaToken] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [localErr, setLocalErr] = useState<string | null>(null);

  if (token) return <Navigate to="/" replace />;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setLocalErr(null);
    clearError();
    try {
      if (mfaToken) {
        await completeMfa(mfaToken, code.trim());
        return;
      }
      const res = await login(email.trim(), password);
      if (res.mfaRequired && res.mfaToken) setMfaToken(res.mfaToken);
    } catch (err) {
      setLocalErr(err instanceof ApiError ? String(err.detail || err.message) : "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <form className="login-card" onSubmit={onSubmit}>
        <h1>SOC AGENT</h1>
        <p>High-density ops console — queue, Cursor AI, live activity feed.</p>
        {!mfaToken ? (
          <>
            <label htmlFor="email">Email</label>
            <input id="email" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required />
            <label htmlFor="password">Password</label>
            <input id="password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </>
        ) : (
          <>
            <label htmlFor="code">MFA code</label>
            <input id="code" inputMode="numeric" value={code} onChange={(e) => setCode(e.target.value)} required />
          </>
        )}
        {(localErr || error) && <div className="err">{localErr || error}</div>}
        <div style={{ marginTop: "1.25rem" }}>
          <button className="btn btn-primary" type="submit" disabled={busy} style={{ width: "100%" }}>
            {busy ? "Signing in…" : mfaToken ? "Verify MFA" : "Enter console"}
          </button>
        </div>
      </form>
    </div>
  );
}

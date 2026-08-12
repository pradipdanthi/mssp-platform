import { FormEvent, useEffect, useState } from "react";
import { ApiError } from "../api/client";
import { getAdminAiChatStatus, postAdminAiChat } from "../api/admin";
import { useAuth } from "../auth/AuthContext";

type ChatTurn = { role: "user" | "assistant"; text: string; meta?: string };

/**
 * KB-096 Phase 3 — Admin AI Assistant (SOC Q&A).
 * Dark until AI_CHAT_ENABLED=true. Does not replace Threat Intel.
 */
export default function AiAssistantPage() {
  const { logout } = useAuth();
  const [enabled, setEnabled] = useState(false);
  const [statusMessage, setStatusMessage] = useState("Checking AI Assistant…");
  const [tenantCode, setTenantCode] = useState("ALPHAWINCORP-6VS2");
  const [message, setMessage] = useState("");
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getAdminAiChatStatus()
      .then((res) => {
        setEnabled(Boolean(res.enabled));
        setStatusMessage(res.message || (res.enabled ? "Ready" : "Disabled"));
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) {
          logout();
          return;
        }
        setStatusMessage("Unable to load AI Assistant status.");
      });
  }, [logout]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const text = message.trim();
    if (!text || busy) return;
    setBusy(true);
    setError(null);
    setTurns((prev) => [...prev, { role: "user", text }]);
    setMessage("");
    try {
      const res = await postAdminAiChat({
        message: text,
        tenant_short_code: tenantCode.trim() || undefined,
      });
      const meta = res.sources
        ? `scope=${res.scope} · alerts=${res.sources.alerts} · incidents=${res.sources.incidents} · TI IOCs=${res.sources.threat_intel_iocs}`
        : undefined;
      setTurns((prev) => [...prev, { role: "assistant", text: res.answer, meta }]);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      const detail =
        err instanceof ApiError && typeof err.detail === "string"
          ? err.detail
          : "AI Assistant request failed.";
      setError(detail);
      setTurns((prev) => [
        ...prev,
        { role: "assistant", text: detail, meta: "error" },
      ]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page-shell">
      <header className="page-header">
        <div>
          <h1 className="page-title">AI Assistant</h1>
          <p className="page-subtitle">
            Ask about tenants, alerts, incidents, and Threat Intel IOCs. Answers use control-plane
            facts only. Human SOC still finalizes customer visibility and containment.
          </p>
        </div>
      </header>

      <div className="credential-panel" style={{ marginBottom: "1rem" }}>
        <p className="page-subtitle" style={{ marginTop: 0 }}>
          Status: {statusMessage}
        </p>
        {!enabled ? (
          <p className="page-subtitle">
            Leave <code>AI_CHAT_ENABLED=false</code> until Ollama is validated. Enabling does not
            change alert ingest or Threat Intel sync.
          </p>
        ) : null}
      </div>

      <form className="credential-panel" onSubmit={onSubmit}>
        <label className="form-label" htmlFor="ai-tenant">
          Tenant short code (optional for platform counts)
        </label>
        <input
          id="ai-tenant"
          className="form-input"
          value={tenantCode}
          disabled={busy || !enabled}
          onChange={(e) => setTenantCode(e.target.value)}
          placeholder="ALPHAWINCORP-6VS2"
        />
        <label className="form-label" htmlFor="ai-message">
          Question
        </label>
        <textarea
          id="ai-message"
          className="form-input"
          rows={3}
          value={message}
          disabled={busy || !enabled}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="What high alerts are open for this tenant, and any matching Threat Intel?"
        />
        <button type="submit" className="btn-primary" disabled={busy || !enabled || !message.trim()}>
          {busy ? "Thinking…" : "Ask"}
        </button>
        {error ? <p className="state-message state-error">{error}</p> : null}
      </form>

      <div style={{ marginTop: "1.25rem", display: "grid", gap: "0.75rem" }}>
        {turns.map((turn, idx) => (
          <div key={`${turn.role}-${idx}`} className="credential-panel">
            <strong>{turn.role === "user" ? "You" : "Assistant"}</strong>
            {turn.meta ? (
              <p className="page-subtitle" style={{ marginTop: "0.25rem" }}>
                {turn.meta}
              </p>
            ) : null}
            <p style={{ whiteSpace: "pre-wrap", marginBottom: 0 }}>{turn.text}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

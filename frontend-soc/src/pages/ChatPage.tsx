import { FormEvent, useEffect, useRef, useState } from "react";
import { ApiError } from "../api/client";
import { getChatStatus, getTenants, postChat } from "../api/soc";
import { useAuth } from "../auth/AuthContext";

type Turn = { role: "user" | "assistant"; text: string; meta?: string; error?: boolean };

const SUGGESTIONS = [
  "What high alerts need attention right now?",
  "Summarize open incidents and next actions.",
  "Any Secure Edge / WAF blocks that look like real attacks?",
];

export default function ChatPage() {
  const { logout } = useAuth();
  const [enabled, setEnabled] = useState(false);
  const [statusMsg, setStatusMsg] = useState("");
  const [tenant, setTenant] = useState("");
  const [tenants, setTenants] = useState<{ short_code: string; name: string }[]>([]);
  const [message, setMessage] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const threadRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    getChatStatus()
      .then((r) => {
        setEnabled(Boolean(r.enabled));
        setStatusMsg(r.message || "");
      })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) logout();
        setEnabled(false);
        setStatusMsg("Unable to reach Cursor chat status.");
      });
    getTenants()
      .then((r) => setTenants((r.tenants || []).map((t) => ({ short_code: t.short_code, name: t.name }))))
      .catch(() => undefined);
  }, [logout]);

  useEffect(() => {
    threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight, behavior: "smooth" });
  }, [turns, busy]);

  async function send(text: string) {
    const q = text.trim();
    if (!q || busy) return;
    setBusy(true);
    setTurns((t) => [...t, { role: "user", text: q }]);
    setMessage("");
    try {
      const res = await postChat(q, tenant || undefined);
      const sources = res.sources
        ? ` · sources: alerts ${res.sources.alerts ?? 0}, incidents ${res.sources.incidents ?? 0}`
        : "";
      setTurns((t) => [
        ...t,
        {
          role: "assistant",
          text: res.answer,
          meta: `${res.provider || "cursor-agent"}${sources}`,
        },
      ]);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        logout();
        return;
      }
      const detail = e instanceof ApiError ? String(e.detail || e.message) : "Chat failed";
      setTurns((t) => [...t, { role: "assistant", text: detail, error: true }]);
    } finally {
      setBusy(false);
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    void send(message);
  }

  return (
    <div className="chat-layout">
      <div>
        <div className="panel-h" style={{ borderRadius: 14, marginBottom: "0.75rem", border: "1px solid var(--line)" }}>
          <h2>Cursor AI chat</h2>
          <select value={tenant} onChange={(e) => setTenant(e.target.value)} style={{ maxWidth: 260 }}>
            <option value="">Platform-wide context</option>
            {tenants.map((t) => (
              <option key={t.short_code} value={t.short_code}>
                {t.name} ({t.short_code})
              </option>
            ))}
          </select>
        </div>
        <p className="muted" style={{ margin: "0 0 0.75rem" }}>
          {enabled ? "Powered by Cursor subscription on the SOC Agent VM." : statusMsg}
        </p>
        <div className="suggestions">
          {SUGGESTIONS.map((s) => (
            <button key={s} type="button" className="chip" disabled={!enabled || busy} onClick={() => void send(s)}>
              {s}
            </button>
          ))}
        </div>
        <div className="thread" ref={threadRef}>
          {turns.length === 0 && <div className="empty">Ask the SOC agent anything about live alerts, incidents, or edge events.</div>}
          {turns.map((t, i) => (
            <div key={i} className={`bubble ${t.role}${t.error ? " err" : ""}`}>
              {t.text}
              {t.meta && <div className="muted" style={{ marginTop: "0.4rem", fontSize: "0.8rem" }}>{t.meta}</div>}
            </div>
          ))}
          {busy && <div className="bubble assistant muted">Cursor is thinking…</div>}
        </div>
      </div>
      <form className="composer" onSubmit={onSubmit}>
        <textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder={enabled ? "Ask the SOC agent…" : "Configure SOC_AGENT_* to enable Cursor chat"}
          disabled={!enabled || busy}
        />
        <button className="btn btn-primary" type="submit" disabled={!enabled || busy || message.trim().length < 3}>
          Send
        </button>
      </form>
    </div>
  );
}

import { FormEvent, KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import { ApiError } from "../api/client";
import { getAdminAiChatStatus, getTenants, postAdminAiChat } from "../api/admin";
import { useAuth } from "../auth/AuthContext";
import {
  getStoredTenantFilter,
  TENANT_FILTER_EVENT,
} from "../components/TenantSwitcher";

type ChatTurn = {
  role: "user" | "assistant";
  text: string;
  meta?: string;
  error?: boolean;
};

const SUGGESTIONS = [
  "What high alerts are open for this tenant?",
  "Summarize open incidents and risk.",
  "Any malicious Threat Intel IOCs matching recent alerts?",
];

/**
 * KB-096 Phase 3 — Admin AI Assistant (SOC Q&A).
 * Uses the header Customer scope switcher (same as Dashboard).
 */
export default function AiAssistantPage() {
  const { logout } = useAuth();
  const [enabled, setEnabled] = useState(false);
  const [tenantFilter, setTenantFilter] = useState(getStoredTenantFilter);
  const [tenants, setTenants] = useState<{ id: string; name: string; short_code: string }[]>([]);
  const [message, setMessage] = useState("");
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const threadRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    getAdminAiChatStatus()
      .then((res) => setEnabled(Boolean(res.enabled)))
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) {
          logout();
          return;
        }
        setEnabled(false);
        setError("Unable to reach AI Assistant.");
      });
  }, [logout]);

  useEffect(() => {
    let cancelled = false;
    getTenants({ page_size: 200 })
      .then((res) => {
        if (cancelled) return;
        setTenants(
          (res.tenants || []).map((t) => ({
            id: t.id,
            name: t.name,
            short_code: t.short_code,
          }))
        );
      })
      .catch(() => {
        /* keep empty list; chat can still run platform-wide */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const onTenant = (e: Event) => {
      const detail = (e as CustomEvent<string>).detail;
      if (typeof detail === "string") {
        setTenantFilter(detail);
        // Clear thread so answers are not mixed across tenants.
        setTurns([]);
        setError(null);
      }
    };
    window.addEventListener(TENANT_FILTER_EVENT, onTenant as EventListener);
    return () => window.removeEventListener(TENANT_FILTER_EVENT, onTenant as EventListener);
  }, []);

  useEffect(() => {
    const el = threadRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [turns, busy]);

  const selectedTenant = useMemo(
    () => (tenantFilter === "all" ? null : tenants.find((t) => t.id === tenantFilter) || null),
    [tenantFilter, tenants]
  );

  const scopeLabel = selectedTenant
    ? `${selectedTenant.name} (${selectedTenant.short_code})`
    : "All tenants";

  async function ask(text: string) {
    const q = text.trim();
    if (!q || busy || !enabled) return;
    setBusy(true);
    setError(null);
    setTurns((prev) => [...prev, { role: "user", text: q }]);
    setMessage("");
    try {
      const res = await postAdminAiChat({
        message: q,
        tenant_id: selectedTenant?.id,
        tenant_short_code: selectedTenant?.short_code,
      });
      const meta = res.sources
        ? `${res.sources.alerts} alerts · ${res.sources.incidents} incidents · ${res.sources.threat_intel_iocs} TI`
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
          : "Request failed.";
      setError(detail);
      setTurns((prev) => [
        ...prev,
        { role: "assistant", text: detail, error: true },
      ]);
    } finally {
      setBusy(false);
      inputRef.current?.focus();
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    void ask(message);
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void ask(message);
    }
  }

  return (
    <div className="ai-chat-page">
      <header className="ai-chat-topbar">
        <div className="ai-chat-topbar-title">
          <h1 className="ai-chat-title">AI Assistant</h1>
          <span
            className={
              "ai-chat-status-pill" + (enabled ? " is-online" : " is-offline")
            }
          >
            {enabled ? "Online" : "Offline"}
          </span>
        </div>
        <div className="ai-chat-tenant" title="Change customer from the header Customer scope control">
          <span className="ai-chat-tenant-label">Scope</span>
          <span className="ai-chat-tenant-value">{scopeLabel}</span>
        </div>
      </header>

      <div className="ai-chat-shell">
        <div className="ai-chat-thread" ref={threadRef} aria-live="polite">
          {turns.length === 0 ? (
            <div className="ai-chat-empty">
              <p className="ai-chat-empty-lead">SOC workspace Q&amp;A</p>
              <p className="ai-chat-empty-copy">
                Answers follow the header <strong>Customer scope</strong> — currently{" "}
                <strong>{scopeLabel}</strong>. Switch tenant there, then ask.
              </p>
              <div className="ai-chat-suggestions">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    type="button"
                    className="ai-chat-suggestion"
                    disabled={!enabled || busy}
                    onClick={() => void ask(s)}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            turns.map((turn, idx) => (
              <div
                key={`${turn.role}-${idx}`}
                className={
                  "ai-chat-bubble" +
                  (turn.role === "user" ? " is-user" : " is-assistant") +
                  (turn.error ? " is-error" : "")
                }
              >
                <div className="ai-chat-bubble-role">
                  {turn.role === "user" ? "You" : "Assistant"}
                </div>
                <div className="ai-chat-bubble-body">{turn.text}</div>
                {turn.meta ? (
                  <div className="ai-chat-bubble-meta">{turn.meta}</div>
                ) : null}
              </div>
            ))
          )}
          {busy ? (
            <div className="ai-chat-bubble is-assistant is-typing">
              <div className="ai-chat-bubble-role">Assistant</div>
              <div className="ai-chat-typing" aria-label="Thinking">
                <span />
                <span />
                <span />
              </div>
            </div>
          ) : null}
        </div>

        <form className="ai-chat-composer" onSubmit={onSubmit}>
          <textarea
            ref={inputRef}
            className="ai-chat-input"
            rows={2}
            value={message}
            disabled={!enabled || busy}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder={
              enabled
                ? `Ask about ${scopeLabel}… (Enter to send)`
                : "AI Assistant is offline"
            }
          />
          <button
            type="submit"
            className="ai-chat-send"
            disabled={!enabled || busy || !message.trim()}
          >
            {busy ? "…" : "Send"}
          </button>
        </form>
        {error ? <p className="ai-chat-error">{error}</p> : null}
      </div>
    </div>
  );
}

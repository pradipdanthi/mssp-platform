/**
 * Dashboard command bridge.
 *
 * TIA asks the dashboard to open an alert by issuing a command. This module is the only
 * place that turns that request into a navigation and, crucially, reports back WHICH
 * alert the page really loaded. The server compares that id with the target; only then
 * does TIA say the alert is open. It lives outside React so it survives the chat panel
 * unmounting when the route changes.
 *
 * Guarantees implemented here (and unit-tested in uiBridge.test.ts):
 *  - a command id is acted on once, however many times it is delivered (reconnect, retry);
 *  - success is reported only from the id of the page that loaded, never from the request;
 *  - a failed load or a timeout is reported, never silently dropped;
 *  - acknowledgement retries are safe because the server treats them as idempotent.
 */

export type UiCommand = {
  id: string;
  type: "open_case";
  payload: { alert_id: string; title?: string; short_code?: string; severity?: string; path?: string };
  status?: string;
  deliver_by?: string;
};

export type AckResult = {
  status: "acknowledged" | "failed" | "expired";
  verified: boolean;
  text?: string;
  spoken?: string;
  reason?: string;
  selected_alert_id?: string;
};

export type BridgeEvent =
  | { kind: "confirmed"; commandId: string; text: string; spoken: string; ms: number }
  | { kind: "failed"; commandId: string; text: string; spoken: string; reason: string }
  | { kind: "navigating"; commandId: string; alertId: string };

export type BridgeDeps = {
  ack: (commandId: string, body: { loaded_alert_id?: string; failure?: string }) => Promise<AckResult>;
  detailPath: (alertId: string) => string;
  now?: () => number;
  setTimer?: (fn: () => void, ms: number) => unknown;
  clearTimer?: (h: unknown) => void;
  waitForLoadMs?: number;
  ackRetries?: number;
  retryDelayMs?: number;
};

type Pending = { cmd: UiCommand; startedAt: number; timer: unknown };

export function createUiBridge(deps: BridgeDeps) {
  const now = deps.now ?? (() => Date.now());
  const setTimer = deps.setTimer ?? ((fn, ms) => setTimeout(fn, ms));
  const clearTimer = deps.clearTimer ?? ((h) => clearTimeout(h as ReturnType<typeof setTimeout>));
  const waitForLoadMs = deps.waitForLoadMs ?? 20000;
  const ackRetries = deps.ackRetries ?? 3;
  const retryDelayMs = deps.retryDelayMs ?? 500;

  const pending = new Map<string, Pending>();
  const finished = new Set<string>();
  const listeners = new Set<(e: BridgeEvent) => void>();
  let loadedAlertId: string | null = null;
  let chatMounted = false;

  const emit = (e: BridgeEvent) => listeners.forEach((l) => l(e));

  async function sendAck(p: Pending, body: { loaded_alert_id?: string; failure?: string }): Promise<void> {
    const id = p.cmd.id;
    if (finished.has(id)) return;
    finished.add(id); // set first: a second page-load event must not post a second acknowledgement
    pending.delete(id);
    clearTimer(p.timer);
    let lastError = "";
    for (let attempt = 0; attempt <= ackRetries; attempt += 1) {
      try {
        const res = await deps.ack(id, body);
        if (res.verified && res.status === "acknowledged") {
          emit({
            kind: "confirmed",
            commandId: id,
            text: res.text || "Confirmed: the alert is open on your screen.",
            spoken: res.spoken || res.text || "It is open.",
            ms: now() - p.startedAt,
          });
        } else {
          const text = res.text || "I can't confirm the alert is on your screen.";
          emit({ kind: "failed", commandId: id, text, spoken: res.spoken || text, reason: res.reason || res.status });
        }
        return;
      } catch (e) {
        lastError = e instanceof Error ? e.message : "ack failed";
        if (attempt < ackRetries) await new Promise((r) => (setTimer(() => r(null), retryDelayMs * (attempt + 1)), undefined));
      }
    }
    const text = "I could not report back to the server, so I can't confirm the alert is on your screen.";
    emit({ kind: "failed", commandId: id, text, spoken: text, reason: `ack_unreachable:${lastError}`.slice(0, 80) });
  }

  return {
    /** Act on a command from the server. Safe to call repeatedly with the same command. */
    register(cmd: UiCommand, navigate: (path: string) => void): "started" | "duplicate" | "unsupported" {
      if (cmd.type !== "open_case" || !cmd.payload?.alert_id) return "unsupported";
      if (pending.has(cmd.id) || finished.has(cmd.id)) return "duplicate";
      const startedAt = now();
      const timer = setTimer(() => {
        const p = pending.get(cmd.id);
        if (p) void sendAck(p, { failure: "page_did_not_load" });
      }, waitForLoadMs);
      const p: Pending = { cmd, startedAt, timer };
      pending.set(cmd.id, p);
      const target = cmd.payload.alert_id;
      if (loadedAlertId === target) {
        void sendAck(p, { loaded_alert_id: loadedAlertId });
      } else {
        emit({ kind: "navigating", commandId: cmd.id, alertId: target });
        navigate(deps.detailPath(target));
      }
      return "started";
    },
    /** The alert page finished loading and shows this alert id. */
    alertLoaded(alertId: string): void {
      loadedAlertId = alertId;
      for (const p of Array.from(pending.values())) {
        // Only the page the command asked for confirms it. An unrelated page finishing
        // loading must not fail the command; the timeout reports "page_did_not_load".
        if (p.cmd.payload.alert_id === alertId) void sendAck(p, { loaded_alert_id: alertId });
      }
    },
    alertLoadFailed(alertId: string, reason: string): void {
      for (const p of Array.from(pending.values())) {
        if (p.cmd.payload.alert_id === alertId) void sendAck(p, { failure: reason });
      }
    },
    alertUnloaded(alertId: string): void {
      if (loadedAlertId === alertId) loadedAlertId = null;
    },
    loadedAlert: () => loadedAlertId,
    pendingCount: () => pending.size,
    setChatMounted(v: boolean): void {
      chatMounted = v;
    },
    chatMounted: () => chatMounted,
    subscribe(l: (e: BridgeEvent) => void): () => void {
      listeners.add(l);
      return () => listeners.delete(l);
    },
  };
}

export type UiBridge = ReturnType<typeof createUiBridge>;

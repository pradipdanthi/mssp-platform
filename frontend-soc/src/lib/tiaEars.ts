/**
 * Always-on ears for Tia.
 * Prefer Chrome continuous SpeechRecognition (reliable wake phrases).
 * Fall back to VAD + server STT when browser recognition is unavailable.
 */

import { blobToBase64 } from "./micCapture";
import {
  HandsFreePhase,
  HandsFreeSession,
  isGoodbye,
  matchWake,
  startHandsFree,
} from "./tiaHandsFree";
import { ensureMicPermission, getSpeechRecognitionCtor, type SpeechRecognitionLike } from "./voice";

export type EarsHandlers = {
  onPhase: (phase: HandsFreePhase, detail?: string) => void;
  /** Final transcript ready for wake/conversation handling */
  onText: (text: string, meta: { inConversation: boolean; source: "browser" | "server" }) => void | Promise<void>;
  onInterim?: (text: string) => void;
  onError: (code: string) => void;
};

export type EarsSession = {
  stop: () => Promise<void>;
  setMuted: (muted: boolean) => void;
  setBusy: (busy: boolean) => void;
  setInConversation: (active: boolean) => void;
  getInConversation: () => boolean;
  mode: "browser" | "server";
};

type RecCtor = new () => SpeechRecognitionLike;

/** True when the operator likely paused mid-thought (do not act yet). */
export function looksIncompleteUtterance(text: string): boolean {
  const t = (text || "").trim();
  if (!t) return true;

  const { woke, remainder } = matchWake(t);
  const body = (woke ? remainder : t).trim();
  const words = body.split(/\s+/).filter(Boolean);
  // Bare "Hi Tia" / "Hey Tia" is always complete — do not wait on trailing heuristics.
  if (woke && words.length === 0) return false;

  // Clear end-of-sentence markers → treat as finished.
  if (/[.!?…]["')\]]?\s*$/.test(t)) return false;
  // Trailing comma / colon → still going.
  if (/[,;:]\s*$/.test(t)) return true;

  const lower = t.toLowerCase().replace(/['']/g, "'");
  // Function words / conjunctions that almost never end a finished ask.
  // (Checked after bare-wake so "Hi Tia" never stalls.)
  if (
    /\b(and|or|but|so|because|if|when|while|that|which|who|whom|whose|what|where|how|why|to|for|of|the|a|an|my|your|our|their|its|is|are|was|were|am|be|been|being|have|has|had|do|does|did|can|could|would|should|will|shall|may|might|must|with|about|from|into|onto|on|in|at|as|than|then|also|just|please|tell|give|show|list|check|look|need|want|get|make|take|see|find|open|close|update|set|mark|run|start|stop)\s*$/i.test(
      lower
    )
  ) {
    return true;
  }

  // Short follow-on after wake ("Hi Tia status") — wait a beat for more words.
  if (woke && words.length > 0 && words.length < 3) return true;
  if (!woke && words.length > 0 && words.length < 3) return true;
  return false;
}

function settleWaitMs(text: string, inConversation: boolean): number {
  const incomplete = looksIncompleteUtterance(text);
  const { woke, remainder } = matchWake(text);
  const bareWake = woke && !(remainder || "").trim();

  // Bare wake — act quickly (was 1100ms; felt like "not responding").
  if (bareWake && !inConversation) return 450;
  // Mid-sentence / trailing "and|the|to…" — wait for more speech.
  if (incomplete) return inConversation ? 2600 : 2200;
  // Finished-looking sentence — still allow a natural breath pause.
  return inConversation ? 1400 : 1100;
}

async function startBrowserEars(handlers: EarsHandlers): Promise<
  | { ok: true; session: EarsSession }
  | { ok: false; code: string }
> {
  const Ctor = getSpeechRecognitionCtor() as RecCtor | null;
  if (!Ctor) return { ok: false, code: "no_browser_stt" };

  const perm = await ensureMicPermission();
  if (perm === "denied" || perm === "unsupported") {
    return { ok: false, code: perm === "unsupported" ? "unsupported" : "denied" };
  }

  let stopped = false;
  let muted = false;
  let hold = false;
  let inConversation = false;
  let restartTimer: number | null = null;
  let debounceTimer: number | null = null;
  let pending = "";
  let hearingLive = false;
  /** When current pending utterance first received speech (ms). */
  let pendingSince = 0;
  let incompleteHolds = 0;
  let rec: SpeechRecognitionLike | null = null;

  const setPhase = (p: HandsFreePhase, detail?: string) => {
    if (!stopped) handlers.onPhase(p, detail);
  };

  const clearTimers = () => {
    if (restartTimer) {
      window.clearTimeout(restartTimer);
      restartTimer = null;
    }
    if (debounceTimer) {
      window.clearTimeout(debounceTimer);
      debounceTimer = null;
    }
  };

  const scheduleFlush = () => {
    if (debounceTimer) window.clearTimeout(debounceTimer);
    const text = pending.trim();
    if (!text) return;
    const wait = settleWaitMs(text, inConversation);
    const incomplete = looksIncompleteUtterance(text);
    setPhase(
      "capturing",
      incomplete ? "Still listening — finish your sentence…" : "Waiting to make sure you're done…"
    );
    debounceTimer = window.setTimeout(() => {
      debounceTimer = null;
      // If interim speech is still flowing, keep holding.
      if (hearingLive) {
        scheduleFlush();
        return;
      }
      const elapsed = pendingSince ? Date.now() - pendingSince : 0;
      // One extra hold if still incomplete — then act so we never stall forever.
      if (looksIncompleteUtterance(pending) && pending.trim() && incompleteHolds < 1 && elapsed < 7000) {
        incompleteHolds += 1;
        scheduleFlush();
        return;
      }
      flushPending();
    }, wait);
  };

  const flushPending = () => {
    const text = pending.trim();
    pending = "";
    hearingLive = false;
    pendingSince = 0;
    incompleteHolds = 0;
    if (!text || stopped || muted || hold) return;
    setPhase("processing", "Got it…");
    void Promise.resolve(
      handlers.onText(text, { inConversation, source: "browser" })
    ).finally(() => {
      if (!stopped && !muted && !hold) {
        setPhase(inConversation ? "in_conversation" : "listening_wake");
      }
    });
  };

  const queueFinal = (piece: string) => {
    const bit = (piece || "").trim();
    if (!bit) return;
    if (!pending.trim()) {
      pendingSince = Date.now();
      incompleteHolds = 0;
    }
    pending = `${pending} ${bit}`.trim();
    incompleteHolds = 0;
    handlers.onInterim?.(pending);
    setPhase("capturing", inConversation ? "Listening…" : "Hearing you…");
    // Chrome often marks mid-sentence chunks as final after a short pause —
    // hold longer and prefer incomplete-sentence detection before acting.
    scheduleFlush();
  };

  const wire = (recognition: SpeechRecognitionLike) => {
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = "en-US";
    recognition.onresult = (ev) => {
      if (muted || hold || stopped) return;
      let interim = "";
      for (let i = ev.resultIndex; i < ev.results.length; i++) {
        const row = ev.results[i];
        const piece = row[0]?.transcript || "";
        if (row.isFinal) queueFinal(piece);
        else interim += piece;
      }
      if (interim.trim()) {
        // Operator is still talking — never flush while interim audio is arriving.
        hearingLive = true;
        incompleteHolds = 0;
        if (debounceTimer) {
          window.clearTimeout(debounceTimer);
          debounceTimer = null;
        }
        handlers.onInterim?.(`${pending} ${interim}`.trim());
        setPhase("capturing", inConversation ? "Listening…" : "Hearing you…");
      } else {
        hearingLive = false;
        // No interim this tick; if we have pending finals, (re)arm settle timer.
        if (pending.trim() && !debounceTimer) scheduleFlush();
      }
    };
    recognition.onerror = (ev) => {
      const code = ev.error || "recognition_error";
      if (code === "aborted" || code === "no-speech") return;
      if (code === "not-allowed") {
        handlers.onError("denied");
        return;
      }
      // network / audio-capture: try restart; surface soft status
      setPhase("listening_wake", `Mic hiccup (${code}) — still listening`);
    };
    recognition.onend = () => {
      if (stopped || muted || hold) return;
      // Chrome ends continuous sessions periodically — auto-restart.
      restartTimer = window.setTimeout(() => {
        restartTimer = null;
        try {
          rec?.start();
        } catch {
          /* already started */
        }
      }, 180);
    };
  };

  const boot = () => {
    rec = new Ctor();
    wire(rec);
    try {
      rec.start();
    } catch (err) {
      return false;
    }
    return true;
  };

  if (!boot()) {
    return { ok: false, code: "busy" };
  }

  setPhase("listening_wake", 'Always listening — say "Hi Tia"');

  const session: EarsSession = {
    mode: "browser",
    stop: async () => {
      stopped = true;
      clearTimers();
      try {
        rec?.abort();
      } catch {
        /* ignore */
      }
      rec = null;
      setPhase("off");
    },
    setMuted: (m: boolean) => {
      muted = m;
      if (m) {
        clearTimers();
        pending = "";
        pendingSince = 0;
        incompleteHolds = 0;
        hearingLive = false;
        try {
          rec?.abort();
        } catch {
          /* ignore */
        }
        setPhase("speaking", "Tia is speaking…");
      } else if (!stopped && !hold) {
        setPhase(inConversation ? "in_conversation" : "listening_wake");
        // Always rebuild after abort — Chrome often won't restart the same instance.
        window.setTimeout(() => {
          if (stopped || muted || hold) return;
          try {
            rec?.abort();
          } catch {
            /* ignore */
          }
          boot();
        }, 120);
      }
    },
    setBusy: (b: boolean) => {
      hold = b;
      if (b) {
        clearTimers();
        pending = "";
        pendingSince = 0;
        incompleteHolds = 0;
        hearingLive = false;
        try {
          rec?.abort();
        } catch {
          /* ignore */
        }
      } else if (!stopped && !muted) {
        setPhase(inConversation ? "in_conversation" : "listening_wake");
        window.setTimeout(() => {
          if (stopped || muted || hold) return;
          try {
            rec?.abort();
          } catch {
            /* ignore */
          }
          boot();
        }, 120);
      }
    },
    setInConversation: (active: boolean) => {
      inConversation = active;
      if (!stopped && !muted && !hold) {
        setPhase(active ? "in_conversation" : "listening_wake");
      }
    },
    getInConversation: () => inConversation,
  };

  return { ok: true, session };
}

async function startServerEars(handlers: EarsHandlers): Promise<
  | { ok: true; session: EarsSession }
  | { ok: false; code: string }
> {
  const { postStt } = await import("../api/soc");
  const started = await startHandsFree({
    onPhase: handlers.onPhase,
    onError: handlers.onError,
    onUtterance: async (wav, meta) => {
      if (wav.size < 600) return;
      try {
        const b64 = await blobToBase64(wav);
        const res = await postStt(b64);
        if (!res.ok || !res.text) {
          handlers.onInterim?.(
            res.reason === "no_speech" ? "Didn't catch that…" : `Voice: ${res.reason || "failed"}`
          );
          return;
        }
        handlers.onInterim?.(res.text);
        await handlers.onText(res.text, {
          inConversation: meta.inConversation,
          source: "server",
        });
      } catch {
        handlers.onError("stt_failed");
      }
    },
  });
  if (!started.ok) return started;

  const inner = started.session;
  const session: EarsSession = {
    mode: "server",
    stop: () => inner.stop(),
    setMuted: (m) => inner.setMuted(m),
    setBusy: (b) => inner.setBusy(b),
    setInConversation: (a) => inner.setInConversation(a),
    getInConversation: () => inner.getInConversation(),
  };
  return { ok: true, session };
}

/** Start always-on listening — browser STT first, server VAD fallback. */
export async function startTiaEars(handlers: EarsHandlers): Promise<
  | { ok: true; session: EarsSession }
  | { ok: false; code: string }
> {
  if (!window.isSecureContext) return { ok: false, code: "insecure" };

  const browser = await startBrowserEars(handlers);
  if (browser.ok) return browser;

  // not-allowed / missing API → try server path (still needs mic for VAD)
  if (browser.code === "denied") {
    // Still try server mic path; same permission usually.
  }
  const server = await startServerEars(handlers);
  if (server.ok) return server;
  return browser.ok === false && browser.code !== "no_browser_stt" ? browser : server;
}

export { isGoodbye, matchWake };
export type { HandsFreePhase, HandsFreeSession };

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
  startHandsFree,
} from "./tiaHandsFree";
import { looksIncompleteUtterance, matchWake, settleWaitMs } from "./tiaUtterance";
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

export { looksIncompleteUtterance, settleWaitMs } from "./tiaUtterance";

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
      incomplete ? "Still with you — go on…" : "Listening through the pause…"
    );
    debounceTimer = window.setTimeout(() => {
      debounceTimer = null;
      // If interim speech is still flowing, keep holding.
      if (hearingLive) {
        scheduleFlush();
        return;
      }
      // One longer hold only when the last word is clearly unfinished.
      if (looksIncompleteUtterance(pending) && pending.trim() && incompleteHolds < 1) {
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

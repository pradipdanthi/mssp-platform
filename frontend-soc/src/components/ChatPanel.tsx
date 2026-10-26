import { FormEvent, KeyboardEvent, useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../api/client";
import { getChatStatus, getTenants, getWakeBriefing, postChat, speakTia } from "../api/soc";
import { useAuth } from "../auth/AuthContext";
import { useOps } from "../state/OpsContext";
import {
  EarsSession,
  HandsFreePhase,
  isGoodbye,
  matchWake,
  startTiaEars,
} from "../lib/tiaEars";
import { micPermissionState } from "../lib/tiaHandsFree";
import {
  beginBriefingTurn,
  briefingRecentlySpoken,
  endBriefingTurn,
  isBriefingAsk,
  isWakeBriefingText,
  markBriefingSpoken,
  noteSpokenLine,
  shouldSpeakLine,
} from "../lib/tiaBriefingGate";
import { playBase64Audio, speakText, stopSpeaking, voiceSupported } from "../lib/voice";

type Turn = { role: "user" | "assistant"; text: string; meta?: string; error?: boolean };

const SHORTCUTS = [
  "Hi Tia, any critical alerts while I was away?",
  "Is the Wazuh manager healthy?",
  "How much RAM does mssp-control have?",
  "What's Shuffle's status?",
];

const CONVO_IDLE_MS = 180000;
const AUTO_KEY = "tia_always_listen";

export default function ChatPanel() {
  const { logout } = useAuth();
  const { selectedAlert } = useOps();
  const [enabled, setEnabled] = useState(false);
  const [statusMsg, setStatusMsg] = useState("");
  const [neuralTts, setNeuralTts] = useState(false);
  const [serverStt, setServerStt] = useState(true);
  const [tenant, setTenant] = useState("");
  const [tenants, setTenants] = useState<{ short_code: string; name: string }[]>([]);
  const [message, setMessage] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [voiceOut, setVoiceOut] = useState(true);
  const [autoApprove, setAutoApprove] = useState(false);
  const autoApproveRef = useRef(false);
  const [listening, setListening] = useState(false);
  const [earsMode, setEarsMode] = useState<"browser" | "server" | "">("");
  const [needMicGate, setNeedMicGate] = useState(false);
  const [phase, setPhase] = useState<HandsFreePhase>("off");
  const [phaseDetail, setPhaseDetail] = useState("");
  const [interim, setInterim] = useState("");
  const [voiceErr, setVoiceErr] = useState<string | null>(null);
  const threadRef = useRef<HTMLDivElement | null>(null);
  const sessionRef = useRef<EarsSession | null>(null);
  const busyRef = useRef(false);
  const voiceOutRef = useRef(true);
  const neuralTtsRef = useRef(false);
  const supportRef = useRef(voiceSupported());
  const enabledRef = useRef(false);
  const autoTriedRef = useRef(false);
  const idleTimerRef = useRef<number | null>(null);
  const lastWakeAtRef = useRef(0);
  const startListenRef = useRef<() => Promise<void>>(async () => undefined);
  const handleTextRef = useRef<(text: string, meta: { inConversation: boolean }) => Promise<void>>(
    async () => undefined
  );

  useEffect(() => {
    busyRef.current = busy;
  }, [busy]);
  useEffect(() => {
    voiceOutRef.current = voiceOut;
  }, [voiceOut]);
  useEffect(() => {
    autoApproveRef.current = autoApprove;
  }, [autoApprove]);

  useEffect(() => {
    const syncVoice = () => {
      try {
        const raw = localStorage.getItem("tia_voice_settings_v1");
        if (!raw) return;
        const parsed = JSON.parse(raw) as {
          speakResponses?: boolean;
          autoApprove?: boolean;
          freeHand?: boolean;
        };
        if (typeof parsed.speakResponses === "boolean") setVoiceOut(parsed.speakResponses);
        if (typeof parsed.autoApprove === "boolean") setAutoApprove(parsed.autoApprove);
        if (typeof parsed.freeHand === "boolean") {
          localStorage.setItem(AUTO_KEY, parsed.freeHand ? "1" : "0");
          if (parsed.freeHand) {
            if (!sessionRef.current && enabledRef.current) {
              window.setTimeout(() => void startListenRef.current(), 200);
            }
          } else if (sessionRef.current) {
            void sessionRef.current.stop();
            sessionRef.current = null;
            setListening(false);
            setPhase("off");
            setPhaseDetail("");
            setNeedMicGate(true);
          }
        }
      } catch {
        /* ignore */
      }
    };
    syncVoice();
    window.addEventListener("tia-voice-settings", syncVoice as EventListener);
    return () => window.removeEventListener("tia-voice-settings", syncVoice as EventListener);
  }, []);
  useEffect(() => {
    neuralTtsRef.current = neuralTts;
  }, [neuralTts]);
  useEffect(() => {
    enabledRef.current = enabled;
  }, [enabled]);

  const clearIdle = useCallback(() => {
    if (idleTimerRef.current) {
      window.clearTimeout(idleTimerRef.current);
      idleTimerRef.current = null;
    }
  }, []);

  const armIdle = useCallback(() => {
    clearIdle();
    idleTimerRef.current = window.setTimeout(() => {
      const s = sessionRef.current;
      if (!s?.getInConversation()) return;
      s.setInConversation(false);
      setPhaseDetail('Still listening — say "Hi Tia"');
      setTurns((t) => [
        ...t,
        {
          role: "assistant",
          text: "I'm still here, boss — say Hi Tia when you need me.",
          meta: "Tia · standby",
        },
      ]);
    }, CONVO_IDLE_MS);
  }, [clearIdle]);

  const speakAnswer = useCallback(async (spoken: string, fullText: string) => {
    if (!voiceOutRef.current) return;
    const line = (spoken || fullText || "").trim();
    if (!line) return;
    if (!shouldSpeakLine(line)) {
      return;
    }
    noteSpokenLine(line);

    sessionRef.current?.setMuted(true);
    setSpeaking(true);
    const speakJob = async () => {
      if (neuralTtsRef.current) {
        try {
          const audio = await speakTia(line);
          if (audio.available && audio.audio_base64) {
            await playBase64Audio(audio.audio_base64, audio.content_type || "audio/mpeg");
            return;
          }
        } catch {
          /* fall through */
        }
      }
      if (supportRef.current.tts) {
        await speakText(line);
      }
    };
    try {
      await Promise.race([
        speakJob(),
        new Promise<void>((resolve) => window.setTimeout(resolve, 45000)),
      ]);
    } finally {
      setSpeaking(false);
      // Longer gap so Tia's own voice is not captured as the next user turn.
      await new Promise((r) => window.setTimeout(r, 700));
      sessionRef.current?.setMuted(false);
    }
  }, []);

  useEffect(() => {
    const onSpeak = (ev: Event) => {
      const text = (ev as CustomEvent<string>).detail;
      if (typeof text !== "string" || !text.trim()) return;
      if (isWakeBriefingText(text)) {
        if (briefingRecentlySpoken() || !beginBriefingTurn()) return;
        markBriefingSpoken(text);
        void speakAnswer(text, text).finally(() => endBriefingTurn());
        return;
      }
      void speakAnswer(text, text);
    };
    window.addEventListener("tia-speak", onSpeak as EventListener);
    return () => window.removeEventListener("tia-speak", onSpeak as EventListener);
  }, [speakAnswer]);

  const send = useCallback(
    async (raw: string, opts?: { fromVoice?: boolean }) => {
      let q = raw.trim();
      if (!q || busyRef.current) return;
      if (q === "Analyze selected alert" && selectedAlert) {
        q = `Hi Tia, analyze this alert for me. Title: ${selectedAlert.alert_title || selectedAlert.title}. Severity: ${selectedAlert.severity}. Host: ${selectedAlert.destination_host || "unknown"}. Status: ${selectedAlert.status}. What should we do next?`;
      }
      const speakReply = voiceOutRef.current && (Boolean(opts?.fromVoice) || Boolean(sessionRef.current));
      stopSpeaking();
      setSpeaking(false);
      busyRef.current = true;
      setBusy(true);
      sessionRef.current?.setBusy(true);
      setTurns((t) => [...t, { role: "user", text: q }]);
      setMessage("");
      setInterim("");
      try {
        const res = await postChat(q, {
          tenant_short_code: tenant || selectedAlert?.short_code || undefined,
          alert_id: selectedAlert?.id,
          auto_approve: autoApproveRef.current,
        });
        const answer = res.answer || "";
        const spoken = res.spoken_answer || answer;
        const applied = (res.actions_applied || []).filter((a) => a.ok).length;
        const pending = res.pending_approval?.id
          ? ` · Needs You: ${res.pending_approval.summary || res.pending_approval.id}`
          : "";
        if (isWakeBriefingText(spoken) || res.provider === "local-briefing") {
          markBriefingSpoken(spoken);
        }
        setTurns((t) => [
          ...t,
          {
            role: "assistant",
            text: answer,
            meta: `Tia · ${res.provider || "cursor"}${applied ? ` · updated ${applied} ticket(s)` : ""}${pending}`,
          },
        ]);
        if (speakReply) await speakAnswer(spoken, answer);
        if (opts?.fromVoice) armIdle();
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) {
          logout();
          return;
        }
        const rawFail = e instanceof ApiError ? String(e.detail || e.message) : "Chat failed";
        const fail =
          /Expecting property name|JSONDecodeError|char 32\d{3}/i.test(rawFail)
            ? "Sorry boss — my stack context was too large. Try again with a shorter question."
            : rawFail;
        setTurns((t) => [...t, { role: "assistant", text: fail, error: true }]);
        if (speakReply) await speakAnswer(`Sorry boss. ${fail}`, fail);
      } finally {
        busyRef.current = false;
        setBusy(false);
        sessionRef.current?.setBusy(false);
      }
    },
    [selectedAlert, tenant, logout, speakAnswer, armIdle]
  );

  const processTranscript = useCallback(
    async (text: string, inConversation: boolean) => {
      const cleaned = text.trim();
      if (!cleaned) return;

      // Ignore tiny noise / single-letter junk that used to stall the loop.
      const words = cleaned.split(/\s+/).filter(Boolean);
      if (words.length === 1 && cleaned.length < 4 && !/tia|tea|hi|hey|bye/i.test(cleaned)) {
        setInterim("…");
        return;
      }

      if (inConversation && isGoodbye(cleaned)) {
        sessionRef.current?.setInConversation(false);
        clearIdle();
        setTurns((t) => [...t, { role: "user", text: cleaned }]);
        const bye = "Alright boss — say Hi Tia whenever you need me.";
        setTurns((t) => [...t, { role: "assistant", text: bye, meta: "Tia · standby" }]);
        await speakAnswer(bye, bye);
        return;
      }

      if (!inConversation) {
        const { woke, remainder } = matchWake(cleaned);
        if (!woke) {
          setInterim(`Heard “${cleaned}” — say “Hi Tia” to wake me`);
          window.setTimeout(() => setInterim((cur) => (cur.startsWith("Heard") ? "" : cur)), 3500);
          return;
        }

        // Prevent double/triple wake from Chrome splitting finals + routine + chat brief.
        const now = Date.now();
        if (now - lastWakeAtRef.current < 8000) {
          if (remainder && remainder.length >= 3) {
            sessionRef.current?.setInConversation(true);
            armIdle();
            await send(remainder, { fromVoice: true });
            return;
          }
          // Bare re-wake within the window — still acknowledge so it never feels dead.
          sessionRef.current?.setInConversation(true);
          armIdle();
          const short = "Still here, boss — go ahead.";
          setTurns((t) => [
            ...t,
            { role: "user", text: cleaned },
            { role: "assistant", text: short, meta: "Tia · wake" },
          ]);
          await speakAnswer(short, short);
          return;
        }
        lastWakeAtRef.current = now;
        sessionRef.current?.setInConversation(true);
        armIdle();

        // Bare "Hi Tia" → one proactive welcome briefing (alerts + urgency + stack).
        if (!remainder || remainder.length < 2) {
          setTurns((t) => [...t, { role: "user", text: cleaned }]);
          if (briefingRecentlySpoken() || !beginBriefingTurn()) {
            const short = "I'm here, boss — what do you need?";
            setTurns((t) => [...t, { role: "assistant", text: short, meta: "Tia · wake" }]);
            await speakAnswer(short, short);
            return;
          }
          busyRef.current = true;
          setBusy(true);
          sessionRef.current?.setBusy(true);
          try {
            const brief = await getWakeBriefing();
            const answer = brief.answer || "Hello boss — welcome back. I'm ready.";
            const spoken =
              brief.spoken_answer ||
              "Hello boss — welcome back. What do you want to dig into?";
            setTurns((t) => [
              ...t,
              {
                role: "assistant",
                text: answer,
                meta: `Tia · ${brief.provider || "wake"}`,
              },
            ]);
            markBriefingSpoken(spoken);
            await speakAnswer(spoken, answer);
          } catch (e) {
            if (e instanceof ApiError && e.status === 401) {
              logout();
              return;
            }
            const fallback =
              "Hello boss — welcome back. I'm online, but the briefing feed hiccuped. What do you need?";
            setTurns((t) => [...t, { role: "assistant", text: fallback, meta: "Tia · wake", error: true }]);
            markBriefingSpoken(fallback);
            await speakAnswer(fallback, fallback);
          } finally {
            endBriefingTurn();
            busyRef.current = false;
            setBusy(false);
            sessionRef.current?.setBusy(false);
          }
          return;
        }

        // "Hi Tia, <question>" → answer directly (no separate yes-boss ack).
        // Skip re-running the same Hello-boss brief if we just gave it.
        if (briefingRecentlySpoken() && isBriefingAsk(remainder)) {
          const short = "Still here, boss — what do you want to dig into?";
          setTurns((t) => [
            ...t,
            { role: "user", text: cleaned },
            { role: "assistant", text: short, meta: "Tia · wake" },
          ]);
          await speakAnswer(short, short);
          return;
        }
        await send(remainder, { fromVoice: true });
        return;
      }

      // Ask for a repeat on very short unclear utterances instead of guessing.
      if (cleaned.length < 6 && !/\d/.test(cleaned)) {
        const again = "Sorry boss, I didn't catch that — say it one more time?";
        setTurns((t) => [...t, { role: "user", text: cleaned }, { role: "assistant", text: again, meta: "Tia · clarify" }]);
        await speakAnswer(again, again);
        return;
      }

      await send(cleaned, { fromVoice: true });
    },
    [send, speakAnswer, armIdle, clearIdle, logout]
  );

  useEffect(() => {
    handleTextRef.current = async (text, meta) => {
      const cleaned = (text || "").trim();
      const { woke } = matchWake(cleaned);
      // Never drop a wake phrase even if a previous turn left busy stuck.
      if (busyRef.current && !woke) {
        setInterim("Tia is busy — one moment…");
        return;
      }
      if (busyRef.current && woke) {
        busyRef.current = false;
        setBusy(false);
        sessionRef.current?.setBusy(false);
        sessionRef.current?.setMuted(false);
      }
      setVoiceErr(null);
      setInterim(`Heard: ${cleaned}`);
      try {
        await processTranscript(
          cleaned,
          meta.inConversation || Boolean(sessionRef.current?.getInConversation())
        );
      } finally {
        setInterim("");
        // Hard safety: never leave ears muted/busy after a turn.
        busyRef.current = false;
        setBusy(false);
        sessionRef.current?.setBusy(false);
        sessionRef.current?.setMuted(false);
      }
    };
  }, [processTranscript]);

  useEffect(() => {
    if (!busy && !speaking) return;
    const t = window.setTimeout(() => {
      if (busyRef.current || speaking) {
        busyRef.current = false;
        setBusy(false);
        setSpeaking(false);
        stopSpeaking();
        sessionRef.current?.setBusy(false);
        sessionRef.current?.setMuted(false);
        setPhaseDetail('Still listening — say "Hi Tia"');
      }
    }, 35000);
    return () => window.clearTimeout(t);
  }, [busy, speaking]);

  function micHelpMessage(code?: string): string {
    const host = window.location.hostname || "192.168.0.201";
    const httpsUrl = `https://${host}:3443/`;
    if (!window.isSecureContext || code === "insecure") {
      return `Mic needs HTTPS. Open ${httpsUrl} (Advanced → Proceed).`;
    }
    if (code === "denied" || code === "not-allowed") {
      return (
        `Microphone is blocked. Address bar → Site settings → Microphone → Allow → reload.`
      );
    }
    if (code === "no-device") return "No microphone found.";
    if (code === "busy") return "Microphone is in use by another app.";
    if (code === "stt_upstream" || code === "stt_failed" || code === "no_browser_stt") {
      return "Voice recognition unavailable in this browser. Try Chrome/Edge on HTTPS.";
    }
    return code ? `Voice error: ${code}` : "Could not start microphone.";
  }

  const startListening = useCallback(async () => {
    setVoiceErr(null);
    if (!window.isSecureContext) {
      setVoiceErr(micHelpMessage("insecure"));
      setNeedMicGate(true);
      return;
    }
    if (!enabledRef.current) return;
    if (sessionRef.current) return;

    setPhase("starting");
    setPhaseDetail("Starting always-on mic…");
    const started = await startTiaEars({
      onPhase: (p, detail) => {
        setPhase(p);
        if (detail) setPhaseDetail(detail);
      },
      onInterim: (t) => setInterim(t),
      onText: (text, meta) => handleTextRef.current(text, meta),
      onError: (code) => setVoiceErr(micHelpMessage(code)),
    });
    if (!started.ok) {
      setPhase("error");
      setListening(false);
      setNeedMicGate(true);
      setVoiceErr(micHelpMessage(started.code));
      return;
    }
    sessionRef.current = started.session;
    setEarsMode(started.session.mode);
    setListening(true);
    setNeedMicGate(false);
    try {
      localStorage.setItem(AUTO_KEY, "1");
    } catch {
      /* ignore */
    }
    setPhase("listening_wake");
    setPhaseDetail(
      started.session.mode === "browser"
        ? 'Always listening — say "Hi Tia"'
        : 'Always listening (server ears) — say "Hi Tia"'
    );
  }, []);

  startListenRef.current = startListening;

  const stopListening = useCallback(async () => {
    clearIdle();
    const s = sessionRef.current;
    sessionRef.current = null;
    setListening(false);
    setEarsMode("");
    setPhase("off");
    setPhaseDetail("");
    setInterim("");
    if (s) await s.stop();
  }, [clearIdle]);

  useEffect(() => {
    getChatStatus()
      .then(async (r) => {
        setEnabled(Boolean(r.enabled));
        setStatusMsg(r.message || "");
        setNeuralTts(Boolean(r.neural_tts));
        setServerStt(r.server_stt !== false);
        enabledRef.current = Boolean(r.enabled);

        if (!r.enabled || !window.isSecureContext) {
          if (!window.isSecureContext) setNeedMicGate(true);
          return;
        }

        const perm = await micPermissionState();
        let preferAuto = true;
        try {
          preferAuto = localStorage.getItem(AUTO_KEY) !== "0";
        } catch {
          preferAuto = true;
        }

        if (!preferAuto) {
          setNeedMicGate(true);
          return;
        }

        if (perm === "denied") {
          setNeedMicGate(true);
          setVoiceErr(micHelpMessage("denied"));
          return;
        }

        if (!autoTriedRef.current) {
          autoTriedRef.current = true;
          window.setTimeout(() => void startListenRef.current(), 350);
        }
      })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) logout();
        setEnabled(false);
      });
    getTenants()
      .then((r) => setTenants((r.tenants || []).map((t) => ({ short_code: t.short_code, name: t.name }))))
      .catch(() => undefined);

    const armGesture = () => {
      if (!sessionRef.current && enabledRef.current) {
        let preferAuto = true;
        try {
          preferAuto = localStorage.getItem(AUTO_KEY) !== "0";
        } catch {
          preferAuto = true;
        }
        if (preferAuto) void startListenRef.current();
      }
    };
    window.addEventListener("pointerdown", armGesture, { capture: true });

    // Watchdog: if Free Hand is on but ears died, restart quietly.
    const watchdog = window.setInterval(() => {
      if (!enabledRef.current || busyRef.current) return;
      let preferAuto = true;
      try {
        preferAuto = localStorage.getItem(AUTO_KEY) !== "0";
      } catch {
        preferAuto = true;
      }
      if (!preferAuto) return;
      if (!sessionRef.current) {
        void startListenRef.current();
      }
    }, 8000);

    return () => {
      window.removeEventListener("pointerdown", armGesture, true);
      window.clearInterval(watchdog);
      if (idleTimerRef.current) window.clearTimeout(idleTimerRef.current);
      void sessionRef.current?.stop();
      sessionRef.current = null;
      stopSpeaking();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [logout]);

  useEffect(() => {
    if (selectedAlert?.short_code) setTenant(selectedAlert.short_code);
  }, [selectedAlert?.short_code]);

  // Command Center quick-command chips → send as a chat turn.
  useEffect(() => {
    const onQuick = (ev: Event) => {
      const detail = (ev as CustomEvent<string>).detail;
      if (typeof detail === "string" && detail.trim().length >= 3) {
        void send(detail.trim(), { fromVoice: false });
      }
    };
    window.addEventListener("tia-quick-command", onQuick as EventListener);
    return () => window.removeEventListener("tia-quick-command", onQuick as EventListener);
  }, [send]);

  useEffect(() => {
    threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight, behavior: "smooth" });
  }, [turns, busy, interim, phase]);

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    void send(message);
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!busy && message.trim().length >= 3) void send(message);
    }
  }

  const statusLine = (() => {
    if (!enabled) return statusMsg;
    if (speaking) return "Tia is speaking…";
    if (busy) return "Tia is checking the stack…";
    if (phase === "capturing") return phaseDetail || "Hearing you…";
    if (phase === "processing") return phaseDetail || "Got it…";
    if (phase === "in_conversation") return 'Talk naturally — say "goodbye Tia" to pause';
    if (phase === "listening_wake" || listening) {
      return earsMode === "browser"
        ? 'On air — say "Hi Tia" (browser ears)'
        : 'On air — say "Hi Tia"';
    }
    if (needMicGate) return "Allow the microphone once — then Tia stays listening";
    if (!window.isSecureContext) return "Open https://192.168.0.201:3443 for always-on voice";
    return "Starting always-on listener…";
  })();

  return (
    <aside className="ops-chat">
      <div className="chat-head">
        <h2>Tia</h2>
        <select value={tenant} onChange={(e) => setTenant(e.target.value)} aria-label="Tenant scope">
          <option value="">All customers</option>
          {tenants.map((t) => (
            <option key={t.short_code} value={t.short_code}>
              {t.short_code}
            </option>
          ))}
        </select>
      </div>
      <div className={`chat-context ${listening ? "live" : ""}`}>{statusLine}</div>
      {voiceErr && <div className="err chat-context">{voiceErr}</div>}
      {needMicGate && !listening && enabled && (
        <div className="chat-context">
          <button type="button" className="btn btn-primary" onClick={() => void startListening()}>
            Allow mic — keep Tia listening
          </button>
        </div>
      )}
      {interim && (
        <div className="interim">
          <em>{interim}</em>
        </div>
      )}

      <div className="thread" ref={threadRef}>
        {turns.length === 0 && (
          <div className="empty">
            Say &quot;Hi Tia&quot; — I&apos;ll welcome you back with alerts, urgency, and stack health, then we talk.
          </div>
        )}
        {turns.map((t, i) => (
          <div key={i} className={`bubble ${t.role}`}>
            {t.text}
            {t.meta && (
              <div className="muted" style={{ marginTop: 4, fontSize: "0.75rem" }}>
                {t.meta}
              </div>
            )}
          </div>
        ))}
        {busy && <div className="bubble assistant muted">Tia is checking the stack…</div>}
      </div>

      <div className="suggestions">
        {SHORTCUTS.map((s) => (
          <button key={s} type="button" className="chip" disabled={!enabled || busy} onClick={() => void send(s)}>
            {s}
          </button>
        ))}
      </div>

      <form className="composer" onSubmit={onSubmit}>
        <textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={onKeyDown}
          rows={2}
          placeholder={enabled ? "Or type… (Enter to send)" : "Tia not configured"}
          disabled={!enabled || busy}
        />
        <div className="composer-actions">
          <button
            type="button"
            className={`btn voice-mic ${listening ? "hot" : "btn-ghost"}`}
            disabled={!enabled}
            onClick={() => {
              if (listening) void stopListening();
              else void startListening();
            }}
            title={listening ? "Mute always-on listener" : "Start always-on listener"}
          >
            {listening ? "On air" : "Listen"}
          </button>
          <button
            type="button"
            className={`btn btn-ghost ${voiceOut ? "" : "off"}`}
            onClick={() => {
              if (voiceOut) {
                stopSpeaking();
                setSpeaking(false);
                sessionRef.current?.setMuted(false);
              }
              setVoiceOut((v) => !v);
            }}
            title={neuralTts ? "Tia voice (neural when configured)" : "Tia voice (browser)"}
          >
            {voiceOut ? "🔊" : "🔇"}
          </button>
          <button className="btn btn-primary" type="submit" disabled={!enabled || busy || message.trim().length < 3}>
            Send
          </button>
        </div>
      </form>
    </aside>
  );
}

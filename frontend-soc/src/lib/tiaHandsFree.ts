/**
 * Always-on hands-free voice for Tia.
 * Mic stays open → adaptive VAD → STT → wake on "Hi Tia" / "Hey Tia" → continuous talk.
 */

import { encodeWavFromFloat32, downsampleTo16k } from "./micWav";

export type HandsFreePhase =
  | "off"
  | "starting"
  | "listening_wake"
  | "in_conversation"
  | "capturing"
  | "processing"
  | "speaking"
  | "error";

export type HandsFreeHandlers = {
  onPhase: (phase: HandsFreePhase, detail?: string) => void;
  onUtterance: (wav: Blob, meta: { inConversation: boolean }) => void | Promise<void>;
  onError: (code: string, detail?: string) => void;
  onLevel?: (rms: number) => void;
};

const MIN_SPEECH_MS = 280;
/** Longer silence so mid-sentence breath pauses do not cut the operator off. */
const SILENCE_END_WAKE_MS = 1400;
const SILENCE_END_CONVO_MS = 2200;
const MAX_UTTERANCE_WAKE_MS = 8000;
const MAX_UTTERANCE_CONVO_MS = 28000;
const PRE_ROLL_MS = 350;

function rms(buf: Float32Array): number {
  let sum = 0;
  for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i];
  return Math.sqrt(sum / Math.max(1, buf.length));
}

export type HandsFreeSession = {
  stop: () => Promise<void>;
  setMuted: (muted: boolean) => void;
  setBusy: (busy: boolean) => void;
  setInConversation: (active: boolean) => void;
  getInConversation: () => boolean;
};

export async function startHandsFree(handlers: HandsFreeHandlers): Promise<
  | { ok: true; session: HandsFreeSession }
  | { ok: false; code: string }
> {
  if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
    return { ok: false, code: "unsupported" };
  }
  if (!window.isSecureContext) {
    return { ok: false, code: "insecure" };
  }

  let stream: MediaStream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        channelCount: 1,
      },
      video: false,
    });
  } catch (err) {
    const name = err instanceof DOMException ? err.name : "NotAllowedError";
    if (name === "NotFoundError" || name === "DevicesNotFoundError") {
      return { ok: false, code: "no-device" };
    }
    if (name === "NotReadableError" || name === "TrackStartError") {
      return { ok: false, code: "busy" };
    }
    return { ok: false, code: "denied" };
  }

  const AudioCtx =
    window.AudioContext ||
    (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
  const ctx = new AudioCtx();
  if (ctx.state === "suspended") {
    try {
      await ctx.resume();
    } catch {
      /* ignore */
    }
  }

  const source = ctx.createMediaStreamSource(stream);
  const processor = ctx.createScriptProcessor(4096, 1, 1);
  // Keep the graph alive without audible playback (Chrome may drop zero-gain chains).
  const sink = ctx.createMediaStreamDestination();
  source.connect(processor);
  processor.connect(sink);

  let stopped = false;
  let muted = false;
  let hold = false;
  let inConversation = false;
  let speaking = false;
  let speechActive = false;
  let speechStartedAt = 0;
  let lastLoudAt = 0;
  let emitting = false;
  let noiseFloor = 0.008;
  const preRoll: Float32Array[] = [];
  let capture: Float32Array[] = [];
  const inputRate = ctx.sampleRate;
  const preRollFrames = Math.max(1, Math.ceil(((PRE_ROLL_MS / 1000) * inputRate) / 4096));

  const setPhase = (p: HandsFreePhase, detail?: string) => {
    if (!stopped) handlers.onPhase(p, detail);
  };

  const flushUtterance = async () => {
    if (emitting || stopped) return;
    const chunks = capture;
    capture = [];
    speechActive = false;
    if (!chunks.length) return;

    let total = 0;
    for (const c of chunks) total += c.length;
    const merged = new Float32Array(total);
    let off = 0;
    for (const c of chunks) {
      merged.set(c, off);
      off += c.length;
    }
    const durationMs = (merged.length / inputRate) * 1000;
    if (durationMs < MIN_SPEECH_MS) {
      setPhase(inConversation ? "in_conversation" : "listening_wake");
      return;
    }

    emitting = true;
    setPhase("processing", "Transcribing…");
    try {
      const down = downsampleTo16k(merged, inputRate);
      const wav = encodeWavFromFloat32(down, 16000);
      await handlers.onUtterance(wav, { inConversation });
    } finally {
      emitting = false;
      if (!stopped && !muted && !hold) {
        setPhase(inConversation ? "in_conversation" : "listening_wake");
      }
    }
  };

  processor.onaudioprocess = (ev) => {
    if (stopped || muted || hold || speaking || emitting) return;
    const input = ev.inputBuffer.getChannelData(0);
    const copy = new Float32Array(input);
    const level = rms(copy);
    handlers.onLevel?.(level);
    const now = performance.now();

    // Adaptive noise floor while idle (slow rise/fall).
    if (!speechActive) {
      noiseFloor = noiseFloor * 0.96 + level * 0.04;
      if (noiseFloor < 0.002) noiseFloor = 0.002;
      if (noiseFloor > 0.04) noiseFloor = 0.04;
    }

    const speechGate = Math.max(0.012, noiseFloor * 3.2);
    const silenceGate = Math.max(0.007, noiseFloor * 1.7);

    preRoll.push(copy);
    while (preRoll.length > preRollFrames + 2) preRoll.shift();

    if (!speechActive) {
      if (level >= speechGate) {
        speechActive = true;
        speechStartedAt = now;
        lastLoudAt = now;
        capture = [...preRoll];
        setPhase("capturing", inConversation ? "Listening…" : "Hearing you…");
      }
      return;
    }

    capture.push(copy);
    if (level >= silenceGate) lastLoudAt = now;

    const spokenMs = now - speechStartedAt;
    const quietMs = now - lastLoudAt;
    const maxMs = inConversation ? MAX_UTTERANCE_CONVO_MS : MAX_UTTERANCE_WAKE_MS;
    const silenceMs = inConversation ? SILENCE_END_CONVO_MS : SILENCE_END_WAKE_MS;
    if (spokenMs >= maxMs || quietMs >= silenceMs) {
      void flushUtterance();
    }
  };

  setPhase("listening_wake", 'Listening for "Hi Tia"');

  const session: HandsFreeSession = {
    stop: async () => {
      if (stopped) return;
      stopped = true;
      try {
        processor.disconnect();
        source.disconnect();
      } catch {
        /* ignore */
      }
      stream.getTracks().forEach((t) => t.stop());
      try {
        await ctx.close();
      } catch {
        /* ignore */
      }
      setPhase("off");
    },
    setMuted: (m: boolean) => {
      muted = m;
      speaking = m;
      if (m) {
        speechActive = false;
        capture = [];
        setPhase("speaking", "Tia is speaking…");
      } else if (!stopped && !hold) {
        setPhase(inConversation ? "in_conversation" : "listening_wake");
      }
    },
    setBusy: (b: boolean) => {
      hold = b;
      if (b) {
        speechActive = false;
        capture = [];
      } else if (!stopped && !muted) {
        setPhase(inConversation ? "in_conversation" : "listening_wake");
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

/** Name variants Google STT often returns for "Tia". */
const TIA_NAME = String.raw`(?:tia|tea|teah|thea|tiya|tiaa|tiaah|tia'|t\.?\s*i\.?\s*a)`;
const GREET = String.raw`(?:hey|hi|hello|ok|okay|yo|ah|oh)`;

const WAKE_RE = new RegExp(
  String.raw`\b${GREET}\s+${TIA_NAME}\b|\b${TIA_NAME}\b[,!]?(?:\s|$)`,
  "i"
);

const GOODBYE_RE =
  /\b(?:goodbye|good\s*bye|bye)\s*(?:tia|tea|teya)?\b|\b(?:that'?s\s*all|stop\s*listening|go\s*to\s*sleep|end\s*conversation|talk\s*later)\b/i;

export function matchWake(text: string): { woke: boolean; remainder: string } {
  const raw = (text || "").trim();
  if (!raw) return { woke: false, remainder: "" };
  const norm = raw.replace(/[^\w\s']/g, " ").replace(/\s+/g, " ").trim();

  // "Hi Tia …" / "Hey Tia …"
  const greeter = new RegExp(String.raw`^\s*${GREET}\s+${TIA_NAME}\b[,!. ]*`, "i");
  if (greeter.test(norm)) {
    return { woke: true, remainder: norm.replace(greeter, "").trim() };
  }

  // Bare "Tia" / "Tia, how's Wazuh"
  const bare = new RegExp(String.raw`^\s*${TIA_NAME}\b[,!. ]*`, "i");
  if (bare.test(norm) && norm.length <= 80) {
    return { woke: true, remainder: norm.replace(bare, "").trim() };
  }

  // Fuzzy: greeting + name-like token anywhere in a short phrase (STT mishears).
  const fuzzyName = /\b(tia|tea|teah|thea|tiya|tiaa|dear|tier|chia|dia|sia|via)\b/i;
  const fuzzyGreet = /\b(hi|hey|hello|ok|okay|yo)\b/i;
  if (norm.length <= 48 && fuzzyGreet.test(norm) && fuzzyName.test(norm)) {
    const remainder = norm
      .replace(fuzzyGreet, " ")
      .replace(fuzzyName, " ")
      .replace(/\s+/g, " ")
      .trim();
    return { woke: true, remainder };
  }

  if (WAKE_RE.test(norm)) {
    const remainder = norm
      .replace(new RegExp(String.raw`${GREET}\s+${TIA_NAME}`, "ig"), " ")
      .replace(new RegExp(String.raw`\b${TIA_NAME}\b`, "ig"), " ")
      .replace(/\s+/g, " ")
      .trim();
    return { woke: true, remainder };
  }

  return { woke: false, remainder: raw };
}

export function isGoodbye(text: string): boolean {
  return GOODBYE_RE.test((text || "").trim());
}

export async function micPermissionState(): Promise<"granted" | "denied" | "prompt" | "unknown"> {
  try {
    if (!navigator.permissions?.query) return "unknown";
    const st = await navigator.permissions.query({ name: "microphone" as PermissionName });
    if (st.state === "granted" || st.state === "denied" || st.state === "prompt") return st.state;
  } catch {
    /* Firefox may throw for microphone */
  }
  return "unknown";
}

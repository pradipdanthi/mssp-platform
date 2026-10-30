/** Voice helpers for Tia — prefer neural browser voices; optional server TTS. */

export type SpeechRecognitionLike = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((ev: SpeechRecognitionEventLike) => void) | null;
  onerror: ((ev: { error?: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
};

type SpeechRecognitionEventLike = {
  resultIndex: number;
  results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }>;
};

type RecognitionCtor = new () => SpeechRecognitionLike;

export function getSpeechRecognitionCtor(): RecognitionCtor | null {
  const w = window as Window & {
    SpeechRecognition?: RecognitionCtor;
    webkitSpeechRecognition?: RecognitionCtor;
  };
  return w.SpeechRecognition || w.webkitSpeechRecognition || null;
}

export function voiceSupported(): { stt: boolean; tts: boolean } {
  return {
    stt: Boolean(getSpeechRecognitionCtor()),
    tts: typeof window !== "undefined" && "speechSynthesis" in window,
  };
}

let tiaAudioCtx: AudioContext | null = null;
let tiaSource: AudioBufferSourceNode | null = null;
let tiaPlayer: HTMLAudioElement | null = null;
const playFinishers = new Set<(ok: boolean) => void>();

function finishAllPlay(ok: boolean): void {
  const waiters = [...playFinishers];
  playFinishers.clear();
  waiters.forEach((fn) => fn(ok));
}

const SILENT_WAV =
  "data:audio/wav;base64,UklGRjIAAABXQVZFZm10IBIAAAABAAEAQB8AAEAfAAABAAgAZGF0YQ4AAAAAAAAAAAAAAAAAAA==";

function speakerEl(): HTMLAudioElement {
  if (!tiaPlayer) {
    tiaPlayer = new Audio();
    tiaPlayer.setAttribute("playsinline", "true");
    tiaPlayer.preload = "auto";
    (window as Window & { __tiaAudio?: HTMLAudioElement }).__tiaAudio = tiaPlayer;
  }
  return tiaPlayer;
}

/**
 * Call from a click or tap. Browsers only allow later playback after a
 * user gesture has started an audio element at least once.
 */
export function unlockTiaAudio(): void {
  const el = speakerEl();
  try {
    el.src = SILENT_WAV;
    const started = el.play();
    if (started && typeof started.catch === "function") started.catch(() => undefined);
  } catch {
    /* ignore */
  }
  const AC =
    window.AudioContext ||
    (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!AC) return;
  if (!tiaAudioCtx) tiaAudioCtx = new AC();
  void tiaAudioCtx.resume();
}

export function stopSpeaking(): void {
  if (typeof window !== "undefined" && "speechSynthesis" in window) {
    window.speechSynthesis.cancel();
  }
  if (tiaSource) {
    try {
      tiaSource.stop();
    } catch {
      /* already stopped */
    }
    tiaSource = null;
  }
  const audio = (window as Window & { __tiaAudio?: HTMLAudioElement }).__tiaAudio;
  if (audio) {
    try {
      audio.onended = null;
      audio.onerror = null;
      audio.pause();
    } catch {
      /* ignore */
    }
  }
  // Resolve waiters so barge-in is not stuck on playBase64Audio until onended (or the 45 s race).
  finishAllPlay(false);
}

function pickHumanVoice(): SpeechSynthesisVoice | null {
  if (!("speechSynthesis" in window)) return null;
  const voices = window.speechSynthesis.getVoices() || [];
  if (!voices.length) return null;
  const prefer = [
    /aria/i,
    /jenny/i,
    /sara(h)?/i,
    /samantha/i,
    /google uk english female/i,
    /microsoft.*(zira|aria|jenny)/i,
    /natural/i,
    /neural/i,
    /female/i,
  ];
  for (const re of prefer) {
    const hit = voices.find((v) => re.test(v.name) && /en/i.test(v.lang));
    if (hit) return hit;
  }
  return voices.find((v) => /en(-|_)?us|en(-|_)?gb/i.test(v.lang)) || voices[0] || null;
}

/** Speak with the local English voice. Resolves true only if speech actually started. */
export function speakText(
  text: string,
  opts?: { rate?: number; onend?: () => void; onstart?: () => void }
): Promise<boolean> {
  return new Promise((resolve) => {
    let settled = false;
    const done = (ok: boolean) => {
      if (settled) return;
      settled = true;
      if (ok) opts?.onend?.();
      resolve(ok);
    };
    if (!("speechSynthesis" in window)) {
      done(false);
      return;
    }
    stopSpeaking();
    const cleaned = (text || "")
      .replace(/```[\s\S]*?```/g, " ")
      .replace(/<<<[\s\S]*?>>>/g, " ")
      .replace(/[*_`#>-]+/g, " ")
      .replace(/\s+/g, " ")
      .trim()
      .slice(0, 900);
    if (!cleaned) {
      done(false);
      return;
    }
    const parts = cleaned.split(/(?<=[.!?])\s+/).map((p) => p.trim()).filter(Boolean);
    const chunks = parts.length ? parts : [cleaned];
    let started = false;
    let left = chunks.length;
    const finishOne = () => {
      left -= 1;
      if (left <= 0) done(started);
    };
    const voice = pickHumanVoice();
    const watchdog = window.setTimeout(() => {
      if (!started) {
        try {
          window.speechSynthesis.cancel();
        } catch {
          /* ignore */
        }
        done(false);
      }
    }, 700);
    const queue = () => {
      window.speechSynthesis.cancel();
      window.speechSynthesis.resume();
      chunks.forEach((part, i) => {
        const u = new SpeechSynthesisUtterance(part);
        const v = pickHumanVoice() || voice;
        if (v) u.voice = v;
        u.rate = opts?.rate ?? 1.0;
        u.pitch = 1.02;
        u.lang = v?.lang || "en-US";
        u.onstart = () => {
          if (!started) {
            started = true;
            window.clearTimeout(watchdog);
            opts?.onstart?.();
          }
        };
        u.onend = finishOne;
        u.onerror = finishOne;
        window.speechSynthesis.speak(u);
        if (i === 0) {
          window.setTimeout(() => {
            if (!started) window.speechSynthesis.resume();
          }, 180);
        }
      });
    };
    if (!(window.speechSynthesis.getVoices() || []).length) {
      window.speechSynthesis.onvoiceschanged = () => queue();
      window.setTimeout(queue, 80);
    } else {
      queue();
    }
  });
}

function bytesFromBase64(b64: string): Uint8Array | null {
  try {
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return bytes;
  } catch {
    return null;
  }
}

/**
 * Play Tia's mp3 through a normal audio element.
 * Resolves true after it finishes, false if the browser blocked playback.
 * Call this from a click when a previous attempt returned false.
 */
export function playBase64Audio(
  b64: string,
  contentType = "audio/mpeg",
  opts?: { onend?: () => void; onstart?: () => void }
): Promise<boolean> {
  return new Promise((resolve) => {
    let settled = false;
    const finish = (ok: boolean) => {
      if (settled) return;
      settled = true;
      playFinishers.delete(finish);
      if (ok) opts?.onend?.();
      resolve(ok);
    };
    playFinishers.add(finish);
    const bytes = bytesFromBase64(b64);
    if (!bytes || !bytes.length) {
      finish(false);
      return;
    }
    const el = speakerEl();
    try {
      el.onended = null;
      el.onerror = null;
      el.pause();
    } catch {
      /* ignore */
    }
    const copy = new ArrayBuffer(bytes.byteLength);
    new Uint8Array(copy).set(bytes);
    const blob = new Blob([copy], { type: contentType || "audio/mpeg" });
    const url = URL.createObjectURL(blob);
    const fail = () => {
      URL.revokeObjectURL(url);
      finish(false);
    };
    el.onended = () => {
      URL.revokeObjectURL(url);
      finish(true);
    };
    el.onerror = fail;
    el.src = url;
    const started = el.play();
    if (!started) {
      fail();
      return;
    }
    started
      .then(() => {
        opts?.onstart?.();
      })
      .catch(() => {
        fail();
      });
  });
}

/**
 * Ask Chrome/Edge for microphone access first. SpeechRecognition alone often
 * fails with "not-allowed" on self-signed lab certs without this prompt.
 */
export async function ensureMicPermission(): Promise<"granted" | "denied" | "unsupported"> {
  if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
    return "unsupported";
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    stream.getTracks().forEach((t) => t.stop());
    return "granted";
  } catch (err) {
    const name = err instanceof DOMException ? err.name : "";
    if (name === "NotAllowedError" || name === "PermissionDeniedError" || name === "SecurityError") {
      return "denied";
    }
    return "denied";
  }
}

export function createRecognizer(handlers: {
  onFinal: (text: string) => void;
  onInterim?: (text: string) => void;
  onError?: (msg: string) => void;
  onEnd?: () => void;
}): SpeechRecognitionLike | null {
  const Ctor = getSpeechRecognitionCtor();
  if (!Ctor) return null;
  const rec = new Ctor();
  rec.continuous = false;
  rec.interimResults = true;
  rec.lang = "en-US";
  rec.onresult = (ev) => {
    let interim = "";
    let finalText = "";
    for (let i = ev.resultIndex; i < ev.results.length; i++) {
      const piece = ev.results[i][0].transcript;
      if (ev.results[i].isFinal) finalText += piece;
      else interim += piece;
    }
    if (interim) handlers.onInterim?.(interim);
    if (finalText.trim()) handlers.onFinal(finalText.trim());
  };
  rec.onerror = (ev) => {
    const code = ev.error || "recognition_error";
    if (code === "aborted" || code === "no-speech") {
      handlers.onEnd?.();
      return;
    }
    handlers.onError?.(code);
    handlers.onEnd?.();
  };
  rec.onend = () => handlers.onEnd?.();
  return rec;
}

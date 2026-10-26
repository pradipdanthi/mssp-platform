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

export function stopSpeaking(): void {
  if (typeof window !== "undefined" && "speechSynthesis" in window) {
    window.speechSynthesis.cancel();
  }
  const audio = (window as Window & { __tiaAudio?: HTMLAudioElement }).__tiaAudio;
  if (audio) {
    try {
      audio.pause();
      audio.src = "";
    } catch {
      /* ignore */
    }
  }
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

/** Speak with the most human-sounding local English voice available. Resolves when done. */
export function speakText(
  text: string,
  opts?: { rate?: number; onend?: () => void; onstart?: () => void }
): Promise<void> {
  return new Promise((resolve) => {
    const done = () => {
      opts?.onend?.();
      resolve();
    };
    if (!("speechSynthesis" in window)) {
      done();
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
      done();
      return;
    }
    const u = new SpeechSynthesisUtterance(cleaned);
    const voice = pickHumanVoice();
    if (voice) u.voice = voice;
    u.rate = opts?.rate ?? 0.96;
    u.pitch = 1.05;
    u.lang = voice?.lang || "en-US";
    u.onstart = () => opts?.onstart?.();
    u.onend = () => done();
    u.onerror = () => done();
    const kick = () => window.speechSynthesis.speak(u);
    if (!(window.speechSynthesis.getVoices() || []).length) {
      window.speechSynthesis.onvoiceschanged = () => {
        const v = pickHumanVoice();
        if (v) u.voice = v;
        kick();
      };
      window.setTimeout(kick, 120);
    } else {
      window.setTimeout(kick, 40);
    }
  });
}

/** Play base64 audio from Tia neural TTS when configured. Resolves when done. */
export function playBase64Audio(
  b64: string,
  contentType = "audio/mpeg",
  opts?: { onend?: () => void; onstart?: () => void }
): Promise<void> {
  return new Promise((resolve) => {
    const done = () => {
      opts?.onend?.();
      resolve();
    };
    stopSpeaking();
    try {
      const bin = atob(b64);
      const bytes = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
      const blob = new Blob([bytes], { type: contentType });
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      (window as Window & { __tiaAudio?: HTMLAudioElement }).__tiaAudio = audio;
      audio.onplay = () => opts?.onstart?.();
      audio.onended = () => {
        URL.revokeObjectURL(url);
        done();
      };
      audio.onerror = () => {
        URL.revokeObjectURL(url);
        done();
      };
      void audio.play().catch(() => done());
    } catch {
      done();
    }
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

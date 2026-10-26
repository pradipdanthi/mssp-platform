/** Push-to-talk WAV capture for Tia — works on lab self-signed HTTPS once mic is Allowed. */

import { downsampleTo16k, encodeWavFromFloat32 } from "./micWav";

export type MicCaptureSession = {
  stop: () => Promise<Blob>;
};

export type MicStartResult =
  | { ok: true; session: MicCaptureSession }
  | { ok: false; code: string; detail?: string };

/** Start capturing; call session.stop() to get a mono 16 kHz WAV blob. */
export async function startMicCapture(): Promise<MicStartResult> {
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
        channelCount: 1,
      },
      video: false,
    });
  } catch (err) {
    const name = err instanceof DOMException ? err.name : "NotAllowedError";
    if (name === "NotFoundError" || name === "DevicesNotFoundError") {
      return { ok: false, code: "no-device", detail: name };
    }
    if (name === "NotReadableError" || name === "TrackStartError") {
      return { ok: false, code: "busy", detail: name };
    }
    return { ok: false, code: "denied", detail: name };
  }

  const AudioCtx =
    window.AudioContext ||
    (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
  const ctx = new AudioCtx();
  const source = ctx.createMediaStreamSource(stream);
  const processor = ctx.createScriptProcessor(4096, 1, 1);
  const chunks: Float32Array[] = [];
  const inputRate = ctx.sampleRate;

  processor.onaudioprocess = (ev) => {
    const input = ev.inputBuffer.getChannelData(0);
    chunks.push(new Float32Array(input));
  };
  const mute = ctx.createGain();
  mute.gain.value = 0;
  source.connect(processor);
  processor.connect(mute);
  mute.connect(ctx.destination);

  let stopped = false;
  const session: MicCaptureSession = {
    stop: async () => {
      if (stopped) return encodeWavFromFloat32(new Float32Array(0), 16000);
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
      let total = 0;
      for (const c of chunks) total += c.length;
      const merged = new Float32Array(total);
      let offset = 0;
      for (const c of chunks) {
        merged.set(c, offset);
        offset += c.length;
      }
      const down = downsampleTo16k(merged, inputRate);
      return encodeWavFromFloat32(down, 16000);
    },
  };
  return { ok: true, session };
}

export async function blobToBase64(blob: Blob): Promise<string> {
  const buf = await blob.arrayBuffer();
  const bytes = new Uint8Array(buf);
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

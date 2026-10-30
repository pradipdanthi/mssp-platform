/**
 * One browser tab owns the microphone. A second tab claiming ownership must
 * stop capture and playback in the loser. Closing the owner does not keep
 * listening after the page is gone.
 */

export const VOICE_OWNER_CHANNEL = "tia-voice-owner";

export function newVoiceOwnerId(): string {
  return `vo-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

export type VoiceOwnerHandle = {
  id: string;
  release: () => void;
};

export function claimVoiceOwner(onLost: () => void): VoiceOwnerHandle {
  const id = newVoiceOwnerId();
  const bc = typeof BroadcastChannel !== "undefined" ? new BroadcastChannel(VOICE_OWNER_CHANNEL) : null;
  const onMessage = (ev: MessageEvent) => {
    const data = ev.data || {};
    if (data.type === "claim" && data.id && data.id !== id) {
      onLost();
    }
  };
  bc?.addEventListener("message", onMessage);
  try {
    bc?.postMessage({ type: "claim", id });
  } catch {
    /* ignore */
  }
  try {
    localStorage.setItem(VOICE_OWNER_CHANNEL, id);
  } catch {
    /* ignore */
  }
  return {
    id,
    release: () => {
      try {
        bc?.postMessage({ type: "release", id });
      } catch {
        /* ignore */
      }
      bc?.removeEventListener("message", onMessage);
      bc?.close();
      try {
        if (localStorage.getItem(VOICE_OWNER_CHANNEL) === id) {
          localStorage.removeItem(VOICE_OWNER_CHANNEL);
        }
      } catch {
        /* ignore */
      }
    },
  };
}

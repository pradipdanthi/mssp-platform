/**
 * Barge-in helpers. TIA must keep listening while she speaks so the operator can
 * interrupt playback. Chrome will also transcribe her own TTS; that echo is dropped.
 * A test hook that calls stopSpeaking() is not microphone proof.
 */

export function looksLikeEcho(heard: string, spoken: string): boolean {
  const norm = (s: string) =>
    s
      .toLowerCase()
      .replace(/[^a-z0-9 ]+/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  const a = norm(heard);
  const b = norm(spoken);
  if (!a || !b || a.length < 8) return false;
  // One or two short words are operator commands ("Critical", "Stop it"), not a
  // replay of a long briefing that happens to contain those words.
  const aWords = a.split(" ").filter(Boolean);
  if (aWords.length <= 2 && a.length < 18) return false;
  if (b.includes(a)) return true;
  const head = b.slice(0, Math.min(48, b.length));
  return head.length >= 8 && a.includes(head);
}

export function interruptPlayback(stop: () => void): number {
  const t0 = performance.now();
  stop();
  return Math.round(performance.now() - t0);
}

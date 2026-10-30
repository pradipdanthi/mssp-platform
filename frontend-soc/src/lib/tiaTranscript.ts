/** The visible conversation survives route changes (the chat panel unmounts on the alert page). */

export type TranscriptTurn = { role: "user" | "assistant"; text: string; meta?: string; error?: boolean };

const KEY = "tia_transcript_v1";
const MAX = 40;
export const TRANSCRIPT_EVENT = "tia-transcript";

export function loadTranscript(): TranscriptTurn[] {
  try {
    const raw = sessionStorage.getItem(KEY);
    const parsed = raw ? (JSON.parse(raw) as TranscriptTurn[]) : [];
    return Array.isArray(parsed) ? parsed.slice(-MAX) : [];
  } catch {
    return [];
  }
}

export function saveTranscript(turns: TranscriptTurn[]): void {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(turns.slice(-MAX)));
  } catch {
    /* storage unavailable: the transcript is best effort */
  }
}

export function appendTranscript(turn: TranscriptTurn): void {
  saveTranscript([...loadTranscript(), turn]);
  window.dispatchEvent(new CustomEvent(TRANSCRIPT_EVENT));
}

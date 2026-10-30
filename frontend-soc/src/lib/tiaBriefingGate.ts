/**
 * Prevent Tia from speaking the same welcome briefing multiple times
 * (routine on load + Hi Tia wake + "what needs attention" local brief).
 */

const COOLDOWN_MS = 90_000;
/** Only block an instant double-fire of the same line, not a real repeat ask. */
const SPEAK_DEDUP_MS = 2_500;

let lastBriefingAt = 0;
let lastSpokenNorm = "";
let lastSpokenAt = 0;
let briefingInFlight = false;

function norm(text: string): string {
  return (text || "")
    .toLowerCase()
    .replace(/\s+/g, " ")
    .replace(/[^\w\s—–-]/g, "")
    .trim()
    .slice(0, 160);
}

export function isWakeBriefingText(text: string): boolean {
  const n = norm(text);
  return n.includes("hello boss") && (n.includes("welcome back") || n.includes("needs my attention") || n.includes("critical"));
}

/** True if a welcome briefing was already delivered recently. */
export function briefingRecentlySpoken(): boolean {
  return Date.now() - lastBriefingAt < COOLDOWN_MS;
}

export function markBriefingSpoken(_text?: string): void {
  // Cooldown only. Do not record the line as already spoken — that skipped
  // the real playback on the same turn (text on screen, silence).
  lastBriefingAt = Date.now();
}

export function beginBriefingTurn(): boolean {
  if (briefingInFlight || briefingRecentlySpoken()) return false;
  briefingInFlight = true;
  return true;
}

export function endBriefingTurn(): void {
  briefingInFlight = false;
}

/**
 * Returns false if this exact (or wake-briefing) line should not be spoken again.
 */
export function shouldSpeakLine(text: string): boolean {
  const n = norm(text);
  if (!n) return false;
  const now = Date.now();
  if (n === lastSpokenNorm && now - lastSpokenAt < SPEAK_DEDUP_MS) {
    return false;
  }
  if (isWakeBriefingText(text) && briefingRecentlySpoken()) {
    return false;
  }
  return true;
}

export function noteSpokenLine(text: string): void {
  const n = norm(text);
  if (!n) return;
  lastSpokenNorm = n;
  lastSpokenAt = Date.now();
  if (isWakeBriefingText(text)) {
    lastBriefingAt = Date.now();
  }
}

/** Operator ask that maps to the same local Hello-boss briefing. */
export function isBriefingAsk(text: string): boolean {
  const ql = (text || "").toLowerCase();
  const keys = [
    "what needs my attention",
    "what needs attention",
    "anything i should know",
    "brief me",
    "status overview",
    "what's going on",
    "whats going on",
    "give me a briefing",
    "morning brief",
    "soc brief",
    "sitrep",
  ];
  return keys.some((k) => ql.includes(k));
}

/** Per-tab identity for TIA conversations. The server binds pending actions to this id. */

const KEY = "tia_session_id_v1";

function randomHex(bytes: number): string {
  const buf = new Uint8Array(bytes);
  if (typeof crypto !== "undefined" && crypto.getRandomValues) crypto.getRandomValues(buf);
  else for (let i = 0; i < bytes; i += 1) buf[i] = Math.floor(Math.random() * 256);
  return Array.from(buf, (b) => b.toString(16).padStart(2, "0")).join("");
}

export function tiaSessionId(): string {
  try {
    const existing = sessionStorage.getItem(KEY);
    if (existing && /^[A-Za-z0-9_-]{6,64}$/.test(existing)) return existing;
    const fresh = `s${randomHex(10)}`;
    sessionStorage.setItem(KEY, fresh);
    return fresh;
  } catch {
    return `s${randomHex(10)}`;
  }
}

/** Unique per operator turn; resending the SAME id after a network failure is safe. */
export function newTurnId(): string {
  return `t${Date.now().toString(36)}${randomHex(4)}`;
}

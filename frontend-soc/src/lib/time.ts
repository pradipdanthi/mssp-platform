export function relativeTime(iso: string, nowMs = Date.now()): string {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "—";
  const sec = Math.max(0, Math.round((nowMs - t) / 1000));
  if (sec < 3) return "Just now";
  if (sec < 60) return `${sec}s ago`;
  const min = Math.round(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.round(min / 60);
  if (hr < 48) return `${hr}h ago`;
  return `${Math.round(hr / 24)}d ago`;
}

export function utcStamp(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toISOString().replace("T", " ").replace(/\.\d+Z$/, " UTC");
}

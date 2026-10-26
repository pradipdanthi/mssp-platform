export default function Severity({ value }: { value?: string | null }) {
  const v = (value || "info").toLowerCase();
  return <span className={`sev sev-${v}`}>{v}</span>;
}

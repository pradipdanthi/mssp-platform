import { Link } from "react-router-dom";
import type { MouseEvent } from "react";

type Props = {
  label: string;
  value: string | null | undefined;
  /** Builds `/alerts?key=value` when clicked. */
  filterKey: "rule_id" | "hostname" | "process" | "path" | "q";
  filterBase?: string;
  className?: string;
  mono?: boolean;
};

/** Clickable evidence value that applies a list filter via URL. */
export default function ClickToFilter({
  label,
  value,
  filterKey,
  filterBase = "/alerts",
  className = "",
  mono = true,
}: Props) {
  const text = (value || "").trim();
  if (!text || text === "—") {
    return <span className={className}>{value ?? "—"}</span>;
  }

  const sep = filterBase.includes("?") ? "&" : "?";
  const to = `${filterBase}${sep}${filterKey}=${encodeURIComponent(text)}`;
  const title = `Filter alerts by ${label}: ${text}`;

  function onClick(e: MouseEvent) {
    e.stopPropagation();
  }

  return (
    <Link
      to={to}
      className={`soc-click-filter ${mono ? "cell-mono" : ""} ${className}`.trim()}
      title={title}
      aria-label={title}
      onClick={onClick}
    >
      {text}
    </Link>
  );
}

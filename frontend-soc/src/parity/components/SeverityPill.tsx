import type { MouseEvent } from "react";
import { Link } from "react-router-dom";
import { alertStatusLabel, incidentStatusLabel } from "../utils/socStatusLabels";

type Kind = "severity" | "status" | "priority";

type Props = {
  value: string;
  kind?: Kind;
  /** Explicit navigation target. Overrides auto href. */
  to?: string | null;
  /** When set with interactive, builds `/{base}?severity=` or `?status=` / `?priority=`. */
  filterBase?: "/alerts" | "/incidents" | "/recommendations" | string;
  /** Make pill a clickable filter control (default true for severity). */
  interactive?: boolean;
  /** Optional click handler (e.g. in-dashboard filter). Runs instead of navigation when provided without `to`. */
  onIsolate?: (value: string) => void;
  /** Prevent parent row click (drawer open). Default true when interactive. */
  stopPropagation?: boolean;
  className?: string;
  /** Override displayed text (DB `value` still drives badge class + filter URL). */
  label?: string;
  /** When kind=status, map alert New→Open / Triaged→In Review (default true for /alerts). */
  statusDomain?: "alert" | "incident" | "raw";
};

function resolveStatusLabel(
  value: string,
  statusDomain: "alert" | "incident" | "raw" | undefined,
  filterBase?: string
): string {
  if (statusDomain === "raw") return value;
  if (statusDomain === "incident") return incidentStatusLabel(value);
  if (statusDomain === "alert") return alertStatusLabel(value);
  // Infer from filter base when not specified.
  if (filterBase && filterBase.includes("/incidents")) return incidentStatusLabel(value);
  if (filterBase && filterBase.includes("/alerts")) return alertStatusLabel(value);
  return value;
}

function buildHref(kind: Kind, value: string, filterBase?: string): string | null {
  if (!filterBase) return null;
  const key = (value || "").toLowerCase().trim();
  if (!key) return null;
  const param =
    kind === "status" ? "status" : kind === "priority" ? "priority" : "severity";
  const sep = filterBase.includes("?") ? "&" : "?";
  return `${filterBase}${sep}${param}=${encodeURIComponent(key)}`;
}

function tooltipFor(kind: Kind, value: string): string {
  const label = value || "item";
  if (kind === "severity") return `Click to isolate ${label} items`;
  if (kind === "status") return `Click to filter by status “${label}”`;
  return `Click to filter by priority “${label}”`;
}

/**
 * Solid severity/status/priority pill — clickable isolate control.
 * Stops row click propagation so table drawers stay independent.
 */
export default function SeverityPill({
  value,
  kind = "severity",
  to,
  filterBase,
  interactive,
  onIsolate,
  stopPropagation,
  className = "",
  label,
  statusDomain,
}: Props) {
  const key = (value || "unknown").toLowerCase().replace(/\s+/g, "-");
  const display =
    label ??
    (kind === "status" ? resolveStatusLabel(value, statusDomain, filterBase) : value);
  const isInteractive =
    interactive ?? (kind === "severity" || Boolean(to) || Boolean(onIsolate) || Boolean(filterBase));
  const defaultBase =
    filterBase ??
    (kind === "priority" ? "/recommendations" : kind === "status" ? "/incidents" : "/alerts");
  const href = to ?? (isInteractive && !onIsolate ? buildHref(kind, value, defaultBase) : null);
  const shouldStop = stopPropagation ?? isInteractive;

  const classes = [
    "badge",
    kind === "status" || kind === "priority" ? `badge-${key}` : `badge badge-${key} severity-${key}`,
    isInteractive ? "badge--interactive" : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  const onClick = (e: MouseEvent) => {
    if (shouldStop) e.stopPropagation();
    if (onIsolate) {
      e.preventDefault();
      onIsolate(value);
    }
  };

  const title = isInteractive ? tooltipFor(kind, display) : undefined;

  if (href && !onIsolate) {
    return (
      <Link
        className={classes}
        to={href}
        title={title}
        aria-label={title}
        onClick={onClick}
      >
        {display}
      </Link>
    );
  }

  if (isInteractive) {
    return (
      <button type="button" className={classes} title={title} aria-label={title} onClick={onClick}>
        {display}
      </button>
    );
  }

  return (
    <span className={classes} title={display}>
      {display}
    </span>
  );
}

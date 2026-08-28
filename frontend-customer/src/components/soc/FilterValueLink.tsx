import { Link } from "react-router-dom";

type FilterKey = "rule_id" | "hostname" | "process" | "path" | "q" | "status" | "severity";

type Props = {
  /** List path to filter, e.g. `/alerts` or `/incidents`. */
  base: "/alerts" | "/incidents" | string;
  /** Query param name. */
  param: FilterKey;
  /** Filter value; when empty, renders a dash. */
  value: string | null | undefined;
  /** Optional display text (defaults to value). */
  label?: string;
  className?: string;
};

/**
 * Clickable cell value that navigates to a list page with a facet query param.
 */
export default function FilterValueLink({
  base,
  param,
  value,
  label,
  className = "cell-mono filter-value-link",
}: Props) {
  const trimmed = (value || "").trim();
  if (!trimmed) return <span className={className}>—</span>;

  const href = `${base}?${param}=${encodeURIComponent(trimmed)}`;
  const title = `Filter by ${param.replace(/_/g, " ")} “${trimmed}”`;

  return (
    <Link className={className} to={href} title={title} aria-label={title}>
      {label ?? trimmed}
    </Link>
  );
}

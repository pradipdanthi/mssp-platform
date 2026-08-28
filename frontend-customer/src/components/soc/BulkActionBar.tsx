type BulkAction = {
  id: string;
  label: string;
  tone?: "default" | "danger" | "primary";
  disabled?: boolean;
  onClick: () => void;
};

type Props = {
  selectedCount: number;
  actions: BulkAction[];
  onClear: () => void;
  entityLabel?: string;
};

/** Floating selection bar for bulk triage (customer_admin). */
export default function BulkActionBar({
  selectedCount,
  actions,
  onClear,
  entityLabel = "selected",
}: Props) {
  if (selectedCount < 1) return null;

  return (
    <div className="soc-bulk-bar" role="region" aria-label="Bulk actions" data-testid="bulk-action-bar">
      <span className="soc-bulk-bar__count">
        {selectedCount} {entityLabel}
      </span>
      <div className="soc-bulk-bar__actions">
        {actions.map((action) => (
          <button
            key={action.id}
            type="button"
            className={
              action.tone === "danger"
                ? "btn btn-danger btn-small"
                : action.tone === "primary"
                  ? "btn btn-primary btn-small"
                  : "btn btn-ghost btn-small"
            }
            disabled={action.disabled}
            onClick={action.onClick}
            data-testid={`bulk-action-${action.id}`}
          >
            {action.label}
          </button>
        ))}
        <button type="button" className="btn btn-ghost btn-small" onClick={onClear}>
          Clear
        </button>
      </div>
    </div>
  );
}

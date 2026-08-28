import { FormEvent, useEffect, useState } from "react";

type Props = {
  open: boolean;
  title?: string;
  confirmLabel?: string;
  onClose: () => void;
  onConfirm: (reason: string) => void | Promise<void>;
};

export default function BulkCloseReasonModal({
  open,
  title = "Bulk close alerts",
  confirmLabel = "Close alerts",
  onClose,
  onConfirm,
}: Props) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) {
      setReason("");
      setBusy(false);
    }
  }, [open]);

  if (!open) return null;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!reason.trim() || busy) return;
    setBusy(true);
    try {
      await onConfirm(reason.trim());
      onClose();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-root" role="dialog" aria-modal="true" aria-label={title}>
      <button type="button" className="modal-backdrop" aria-label="Cancel" onClick={onClose} />
      <form className="modal-card card-surface" onSubmit={submit}>
        <h2 className="modal-title">{title}</h2>
        <p className="modal-body">Provide a short reason for closing the selected alerts.</p>
        <label className="list-toolbar-field">
          <span>Reason</span>
          <textarea
            className="form-input"
            rows={3}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            disabled={busy}
            required
            placeholder="e.g. Confirmed benign / remediated"
            data-testid="bulk-close-reason"
          />
        </label>
        <div className="modal-actions">
          <button type="button" className="btn btn-ghost" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={busy || !reason.trim()}>
            {busy ? "Closing…" : confirmLabel}
          </button>
        </div>
      </form>
    </div>
  );
}

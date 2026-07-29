import { FormEvent, useState } from "react";

type Props = {
  open: boolean;
  title: string;
  body: string;
  confirmPhrase: string;
  confirmLabel?: string;
  onCancel: () => void;
  onConfirm: () => void | Promise<void>;
};

export default function ConfirmDangerModal({
  open,
  title,
  body,
  confirmPhrase,
  confirmLabel = "Confirm",
  onCancel,
  onConfirm,
}: Props) {
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  if (!open) return null;
  const ok = typed.trim() === confirmPhrase;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!ok || busy) return;
    setBusy(true);
    try {
      await onConfirm();
      setTyped("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-root" role="dialog" aria-modal="true" aria-label={title}>
      <button type="button" className="modal-backdrop" aria-label="Cancel" onClick={onCancel} />
      <form className="modal-card card-surface" onSubmit={submit}>
        <h2 className="modal-title">{title}</h2>
        <p className="modal-body">{body}</p>
        <p className="modal-hint">
          Type <span className="cell-mono text-cyan">{confirmPhrase}</span> to confirm.
        </p>
        <input
          className="form-input"
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
          autoFocus
          autoComplete="off"
        />
        <div className="modal-actions">
          <button type="button" className="btn btn-ghost" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button type="submit" className="btn btn-danger" disabled={!ok || busy}>
            {busy ? "Working…" : confirmLabel}
          </button>
        </div>
      </form>
    </div>
  );
}

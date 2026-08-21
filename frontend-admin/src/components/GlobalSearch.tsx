import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

const ROUTES: { label: string; path: string; keywords: string }[] = [
  { label: "Dashboard", path: "/dashboard", keywords: "home overview operations" },
  { label: "Incidents", path: "/incidents", keywords: "cases triage" },
  { label: "Alerts", path: "/alerts", keywords: "detections" },
  { label: "Recommendations", path: "/recommendations", keywords: "actions" },
  { label: "Customers", path: "/tenants", keywords: "tenants orgs clients" },
  { label: "Appliances", path: "/appliances", keywords: "sensors collectors" },
  { label: "Vulnerabilities", path: "/vulnerabilities", keywords: "cve scanning" },
  { label: "Compliance", path: "/compliance", keywords: "cis iso pci nist hipaa hardening scorecard" },
  { label: "Reports", path: "/reports", keywords: "monthly" },
  { label: "Notifications", path: "/notifications", keywords: "whatsapp email" },
  { label: "Audit", path: "/audit", keywords: "logs compliance" },
];

/** Cmd/Ctrl+K global search palette (Sentinel-style). */
export default function GlobalSearch({ routes = ROUTES }: { routes?: typeof ROUTES }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen(true);
      }
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (open) {
      setQ("");
      setTimeout(() => inputRef.current?.focus(), 0);
    }
  }, [open]);

  const needle = q.trim().toLowerCase();
  const hits = routes.filter(
    (r) =>
      !needle ||
      r.label.toLowerCase().includes(needle) ||
      r.path.includes(needle) ||
      r.keywords.includes(needle)
  );

  return (
    <>
      <button
        type="button"
        className="global-search-trigger"
        onClick={() => setOpen(true)}
        aria-label="Open search"
      >
        <span>Search</span>
        <kbd>⌘K</kbd>
      </button>
      {open ? (
        <div className="global-search-overlay" role="dialog" aria-modal="true">
          <div className="global-search-modal card-surface">
            <input
              ref={inputRef}
              className="global-search-input"
              placeholder="Search pages, incidents, alerts…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && hits[0]) {
                  navigate(hits[0].path);
                  setOpen(false);
                }
              }}
            />
            <ul className="global-search-results">
              {hits.length === 0 ? (
                <li className="global-search-empty">No matches</li>
              ) : (
                hits.map((r) => (
                  <li key={r.path}>
                    <button
                      type="button"
                      onClick={() => {
                        navigate(r.path);
                        setOpen(false);
                      }}
                    >
                      <span>{r.label}</span>
                      <span className="cell-mono">{r.path}</span>
                    </button>
                  </li>
                ))
              )}
            </ul>
            <p className="global-search-hint">Press Esc to close · Enter to open first result</p>
          </div>
          <button
            type="button"
            className="global-search-backdrop"
            aria-label="Close search"
            onClick={() => setOpen(false)}
          />
        </div>
      ) : null}
    </>
  );
}

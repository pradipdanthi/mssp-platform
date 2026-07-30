import { FormEvent, useEffect, useState } from "react";

export interface ListPaginationMeta {
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  has_next: boolean;
  has_prev: boolean;
}

export interface ListToolbarProps {
  searchPlaceholder?: string;
  searchValue: string;
  onSearchChange: (value: string) => void;
  statusOptions?: { value: string; label: string }[];
  statusValue?: string;
  onStatusChange?: (value: string) => void;
  severityOptions?: { value: string; label: string }[];
  severityValue?: string;
  onSeverityChange?: (value: string) => void;
  pageSize: number;
  onPageSizeChange: (size: number) => void;
  meta?: ListPaginationMeta | null;
  onPageChange: (page: number) => void;
}

const PAGE_SIZES = [25, 50, 100];

export default function ListToolbar({
  searchPlaceholder = "Search…",
  searchValue,
  onSearchChange,
  statusOptions,
  statusValue = "",
  onStatusChange,
  severityOptions,
  severityValue = "",
  onSeverityChange,
  pageSize,
  onPageSizeChange,
  meta,
  onPageChange,
}: ListToolbarProps) {
  const [draft, setDraft] = useState(searchValue);

  useEffect(() => {
    setDraft(searchValue);
  }, [searchValue]);

  function submitSearch(e: FormEvent) {
    e.preventDefault();
    onSearchChange(draft.trim());
  }

  const total = meta?.total ?? 0;
  const page = meta?.page ?? 1;
  const totalPages = meta?.total_pages ?? 0;
  const from = total === 0 ? 0 : (page - 1) * (meta?.page_size ?? pageSize) + 1;
  const to = Math.min(page * (meta?.page_size ?? pageSize), total);

  return (
    <div className="list-toolbar">
      <form className="list-toolbar-filters" onSubmit={submitSearch}>
        <label className="list-toolbar-field">
          <span className="visually-hidden">Search</span>
          <input
            type="search"
            className="list-toolbar-input"
            placeholder={searchPlaceholder}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
          />
        </label>
        <button type="submit" className="btn btn-ghost btn-small">
          Search
        </button>
        {statusOptions && onStatusChange ? (
          <label className="list-toolbar-field">
            <span>Status</span>
            <select
              value={statusValue}
              onChange={(e) => onStatusChange(e.target.value)}
            >
              <option value="">All</option>
              {statusOptions.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        {severityOptions && onSeverityChange ? (
          <label className="list-toolbar-field">
            <span>Severity</span>
            <select
              value={severityValue}
              onChange={(e) => onSeverityChange(e.target.value)}
            >
              <option value="">All</option>
              {severityOptions.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <label className="list-toolbar-field">
          <span>Per page</span>
          <select
            value={pageSize}
            onChange={(e) => onPageSizeChange(Number(e.target.value))}
          >
            {PAGE_SIZES.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
      </form>

      <div className="list-toolbar-pager">
        <span className="list-toolbar-range">
          {total === 0 ? "0 results" : `${from}–${to} of ${total}`}
        </span>
        <button
          type="button"
          className="btn btn-ghost btn-small"
          disabled={!meta?.has_prev}
          onClick={() => onPageChange(page - 1)}
        >
          Previous
        </button>
        <span className="list-toolbar-page">
          Page {totalPages === 0 ? 0 : page} / {totalPages}
        </span>
        <button
          type="button"
          className="btn btn-ghost btn-small"
          disabled={!meta?.has_next}
          onClick={() => onPageChange(page + 1)}
        >
          Next
        </button>
      </div>
    </div>
  );
}

import { useEffect, useRef, useState } from "react";

export type RuleFacetOption = {
  rule_id: string;
  description: string;
  hits: number;
};

type Props = {
  value: string;
  onSelect: (ruleId: string) => void;
  onDraftChange?: (draft: string) => void;
  loadFacets?: (q: string) => Promise<RuleFacetOption[]>;
  disabled?: boolean;
};

/** Searchable Rule ID combobox; selecting a rule immediately applies the filter. */
export default function RuleIdCombobox({
  value,
  onSelect,
  onDraftChange,
  loadFacets,
  disabled,
}: Props) {
  const [draft, setDraft] = useState(value);
  const [open, setOpen] = useState(false);
  const [options, setOptions] = useState<RuleFacetOption[]>([]);
  const [loading, setLoading] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    setDraft(value);
  }, [value]);

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  useEffect(() => {
    if (!loadFacets || !open) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setLoading(true);
      loadFacets(draft.trim())
        .then((rows) => setOptions(rows))
        .catch(() => setOptions([]))
        .finally(() => setLoading(false));
    }, 200);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [draft, open, loadFacets]);

  function apply(ruleId: string) {
    setDraft(ruleId);
    onDraftChange?.(ruleId);
    onSelect(ruleId);
    setOpen(false);
  }

  return (
    <div className="rule-id-combobox" ref={wrapRef}>
      <input
        className="list-toolbar-input list-toolbar-input--narrow"
        data-testid="filter-rule-id"
        value={draft}
        disabled={disabled}
        placeholder={loadFacets ? "Search rule…" : "e.g. 92213"}
        autoComplete="off"
        onFocus={() => setOpen(true)}
        onChange={(e) => {
          const next = e.target.value;
          setDraft(next);
          onDraftChange?.(next);
          setOpen(true);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            apply(draft.trim());
          } else if (e.key === "Escape") {
            setOpen(false);
          }
        }}
      />
      {open && loadFacets ? (
        <ul className="rule-id-combobox__menu" role="listbox">
          {loading ? <li className="rule-id-combobox__empty">Loading…</li> : null}
          {!loading && options.length === 0 ? (
            <li className="rule-id-combobox__empty">
              {draft.trim() ? "No matching rules" : "Type to search rules"}
            </li>
          ) : null}
          {!loading &&
            options.map((opt) => (
              <li key={opt.rule_id}>
                <button
                  type="button"
                  className="rule-id-combobox__option"
                  role="option"
                  onClick={() => apply(opt.rule_id)}
                >
                  <span className="rule-id-combobox__id">{opt.rule_id}</span>
                  <span className="rule-id-combobox__desc">
                    {opt.description || "—"} ({opt.hits} hits)
                  </span>
                </button>
              </li>
            ))}
        </ul>
      ) : null}
    </div>
  );
}

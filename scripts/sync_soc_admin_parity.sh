#!/usr/bin/env bash
# Sync Admin alert/incident/EDR UI into the SOC Agent Console (parity tree).
# Keeps SOC console on the same triage + Isolate actions as the Admin portal.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/frontend-admin/src"
DST="$ROOT/frontend-soc/src/parity"
rm -rf "$DST"
mkdir -p "$DST"

FILES=(
  api/admin.ts
  api/edr.ts
  components/CustomerScopeBanner.tsx
  components/ListToolbar.tsx
  components/RowActionsMenu.tsx
  components/SeverityPill.tsx
  components/TenantSwitcher.tsx
  components/edr/EdrControlPanel.tsx
  components/edr/MitreBadges.tsx
  components/edr/ProcessTreeWidget.tsx
  components/soc/AiSocAssistPanel.tsx
  components/soc/AlertTechnicalEvidence.tsx
  components/soc/BulkActionBar.tsx
  components/soc/BulkCloseReasonModal.tsx
  components/soc/ClickToFilter.tsx
  components/soc/RuleIdCombobox.tsx
  components/soc/SocFilterBar.tsx
  components/soc/SuppressionRuleModal.tsx
  components/soc/ToastProvider.tsx
  components/soc/savedPresets.ts
  config/niktiairBrands.ts
  hooks/useAdminQuery.ts
  hooks/useCustomerScope.ts
  lib/ai-triage.ts
  lib/services/vt-enrichment.ts
  pages/AlertDetailPage.tsx
  pages/AlertsPage.tsx
  pages/IncidentDetailPage.tsx
  pages/IncidentsPage.tsx
  pages/VulnerabilitiesPage.tsx
  pages/CompliancePage.tsx
  pages/SecureEdgePage.tsx
  utils/socStatusLabels.ts
)

# Full Admin visual system so Isolate / triage panels render correctly.
cp "$SRC/styles.css" "$DST/admin-parity.css"

for rel in "${FILES[@]}"; do
  if [[ ! -f "$SRC/$rel" ]]; then
    echo "WARN: missing $rel" >&2
    continue
  fi
  mkdir -p "$DST/$(dirname "$rel")"
  cp "$SRC/$rel" "$DST/$rel"
done

# Point auth + HTTP client at the SOC console modules (shared JWT via setAuthToken).
python3 - "$DST" <<'PY'
from pathlib import Path
import re, sys
root = Path(sys.argv[1])
for path in root.rglob("*"):
    if path.suffix not in {".ts", ".tsx"}:
        continue
    text = path.read_text()
    depth = len(path.relative_to(root).parts) - 1
    prefix = "../" * (depth + 1)  # up to src/
    client = f"{prefix}api/client"
    auth = f"{prefix}auth/AuthContext"
    orig = text
    text = re.sub(
        r'''from\s+(["'])(?:\.\./)+api/client\1''',
        f'from "{client}"',
        text,
    )
    text = re.sub(
        r'''from\s+(["'])(?:\.\./)+auth/AuthContext\1''',
        f'from "{auth}"',
        text,
    )
    # parity/api/*.ts originally imported ./client from admin
    text = re.sub(
        r'''from\s+(["'])\./client\1''',
        f'from "{client}"',
        text,
    )
    if text != orig:
        path.write_text(text)
        print(f"rewrote imports: {path.relative_to(root)}")

# Keep alert/incident Links inside /monitor/:shortCode when on a customer wall.
pages = root / "pages"
for name, replacements in {
    "AlertsPage.tsx": [
        (
            'to={`/alerts/${alert.id}`}',
            'to={alertDetailPath(alert.id)}',
        ),
    ],
    "AlertDetailPage.tsx": [
        ('const backHref = "/alerts";', "const backHref = alertsListPath();"),
    ],
    "IncidentsPage.tsx": [
        (
            'to={`/incidents/${incident.id}`}',
            'to={incidentDetailPath(incident.id)}',
        ),
        (
            "navigate(`/incidents/${incident.id}`)",
            "navigate(incidentDetailPath(incident.id))",
        ),
    ],
    "IncidentDetailPage.tsx": [
        (
            '<Link to="/incidents">← Back to incidents</Link>',
            "<Link to={incidentsListPath()}>← Back to incidents</Link>",
        ),
        (
            "to={`/alerts/${incidentQuery.data.primary_alert.id}`}",
            "to={alertDetailPath(incidentQuery.data.primary_alert.id)}",
        ),
    ],
}.items():
    path = pages / name
    if not path.exists():
        continue
    text = path.read_text()
    orig = text
    for old, new in replacements:
        text = text.replace(old, new)
    if "alertDetailPath" in text or "alertsListPath" in text or "incidentDetailPath" in text or "incidentsListPath" in text:
        if "from \"../../lib/socPaths\"" not in text and "from '../../lib/socPaths'" not in text:
            # insert import after react-router-dom import if present
            m = re.search(r'(import .+ from ["\']react-router-dom["\'];\n)', text)
            inject = (
                'import {\n'
                '  alertDetailPath,\n'
                '  alertsListPath,\n'
                '  incidentDetailPath,\n'
                '  incidentsListPath,\n'
                '} from "../../lib/socPaths";\n'
            )
            if m:
                text = text[: m.end()] + inject + text[m.end() :]
            else:
                text = inject + text
    if text != orig:
        path.write_text(text)
        print(f"rewrote monitor paths: {name}")
PY

echo "OK: synced Admin triage/EDR parity into frontend-soc/src/parity ($(find "$DST" -type f | wc -l) files)"

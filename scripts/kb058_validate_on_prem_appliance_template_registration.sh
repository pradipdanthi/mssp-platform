#!/usr/bin/env bash
set -euo pipefail

cd /opt/mssp-control

fail() {
  echo "VALIDATION FAILED: $1" >&2
  exit 1
}

required=(
  templates/on-prem-appliance/README.md
  templates/on-prem-appliance/docker-compose.yml.template
  backend-api/app/api/routes/on_prem_template.py
  backend-api/app/main.py
  frontend-admin/src/api/appliances.ts
  frontend-admin/src/pages/AppliancesPage.tsx
  docs/KB058_ON_PREM_APPLIANCE_TEMPLATE_REGISTRATION.md
)

for file in "${required[@]}"; do
  [[ -f "$file" ]] || fail "$file is missing"
done

python3 - <<'PY'
import ast
from pathlib import Path

route_path = Path("backend-api/app/api/routes/on_prem_template.py")
tree = ast.parse(route_path.read_text())
values = {}
for node in tree.body:
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in {
                "README_TEXT", "COMPOSE_TEMPLATE_TEXT", "ON_PREM_TEMPLATE_ROLES"
            }:
                values[target.id] = ast.literal_eval(node.value)

if values.get("ON_PREM_TEMPLATE_ROLES") != ("platform_admin", "soc_manager"):
    raise SystemExit("template endpoint roles must be platform_admin and soc_manager only")
if values.get("README_TEXT") != Path(
    "templates/on-prem-appliance/README.md"
).read_text():
    raise SystemExit("README endpoint text differs from shipped template")
if values.get("COMPOSE_TEMPLATE_TEXT") != Path(
    "templates/on-prem-appliance/docker-compose.yml.template"
).read_text():
    raise SystemExit("Compose endpoint text differs from shipped template")
PY

route="backend-api/app/api/routes/on_prem_template.py"
for needle in \
  '/admin/appliances/on-prem-template' \
  'require_roles' \
  'contains_secrets' \
  'README.md' \
  'docker-compose.yml.template'; do
  rg -Fq "$needle" "$route" || fail "$route missing required behavior: $needle"
done

for needle in \
  '<APPLIANCE_IMAGE>' \
  '<CONTROL_PLANE_URL>' \
  '<ACTIVATION_TOKEN>' \
  '<APPLIANCE_NAME>' \
  '<AGENT_VERSION>'; do
  rg -Fq "$needle" templates/on-prem-appliance/docker-compose.yml.template \
    || fail "Compose template missing placeholder: $needle"
done

rg -Fq "on_prem_template_router" backend-api/app/main.py \
  || fail "KB-058 router is not registered in main.py"
rg -Fq "Download on-prem template" frontend-admin/src/pages/AppliancesPage.tsx \
  || fail "Appliances page is missing the template download button"
rg -Fq "getOnPremTemplate" frontend-admin/src/api/appliances.ts \
  || fail "Admin frontend API client is missing getOnPremTemplate"

python3 - <<'PY'
import re
from pathlib import Path

pattern = re.compile(
    r"""(?i)(password|api[_-]?key|activation[_-]?token)\s*[:=]\s*["'](?!<)[^"']{6,}"""
)
for path in (
    Path("templates/on-prem-appliance/README.md"),
    Path("templates/on-prem-appliance/docker-compose.yml.template"),
    Path("docs/KB058_ON_PREM_APPLIANCE_TEMPLATE_REGISTRATION.md"),
):
    if pattern.search(path.read_text()):
        raise SystemExit(f"possible real secret found in {path}")
PY

if git status --porcelain -- .env postgres/init docker-compose.yml frontend-customer 2>/dev/null | rg -q .; then
  fail "KB-058 must not change protected runtime/customer paths"
fi

if docker compose exec -T frontend-admin npm run build; then
  echo "OK: frontend-admin build passed."
else
  fail "frontend-admin build failed"
fi

echo "KB-058 ON-PREM APPLIANCE TEMPLATE REGISTRATION VALIDATION PASSED"

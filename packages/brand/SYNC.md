# Syncing locked brand assets

Canonical source: `packages/brand/` (currently Brand Kit **v1.1.0**).

Install / refresh from kit:

```bash
# copy kit files into packages/brand, then:
./scripts/sync_kevantic_brand.sh
docker compose build frontend-admin frontend-customer
docker compose up -d --force-recreate frontend-admin frontend-customer
```

Do not edit SVG geometry. Do not recreate CYBER SECURITY with HTML/CSS.

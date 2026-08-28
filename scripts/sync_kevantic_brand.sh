#!/usr/bin/env bash
# Copy locked Kevantic brand assets from packages/brand into app public dirs.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/packages/brand"

TARGETS=(
  "$ROOT/frontend-admin/public/brand"
  "$ROOT/frontend-customer/public/brand"
  "$ROOT/website-niktiar/assets/brand"
)

ASSETS=(
  kevantic-horizontal.svg
  kevantic-horizontal-dark.svg
  kevantic-wordmark.svg
  kevantic-mark.svg
  favicon.svg
  favicon.ico
  favicon-16.png
  favicon-32.png
  apple-touch-icon-180.png
  app-icon-512.png
  kevantic-og-1200x630.png
  kevantic-brand.css
  brand-manifest.json
)

for dest in "${TARGETS[@]}"; do
  mkdir -p "$dest"
  for f in "${ASSETS[@]}"; do
    cp -a "$SRC/$f" "$dest/$f"
  done
  # Compatibility aliases used by older validators / paths
  cp -a "$SRC/kevantic-mark.svg" "$dest/kestrel-mark.svg"
  cp -a "$SRC/kevantic-horizontal.svg" "$dest/kestrel-logo.svg"
  cp -a "$SRC/kevantic-horizontal.svg" "$dest/kevantic-logo.svg"
  echo "synced -> $dest"
done

# Website root asset convenience copies for legacy relative paths during transition
WEB="$ROOT/website-niktiar/assets"
cp -a "$SRC/kevantic-horizontal.svg" "$WEB/logo-nav.svg"
cp -a "$SRC/kevantic-mark.svg" "$WEB/mark.svg"
cp -a "$SRC/favicon.svg" "$WEB/favicon.svg"
cp -a "$SRC/favicon.ico" "$WEB/favicon.ico"
cp -a "$SRC/apple-touch-icon-180.png" "$WEB/apple-touch-icon-180.png"
cp -a "$SRC/kevantic-og-1200x630.png" "$WEB/kevantic-og-1200x630.png"
echo "synced website root asset aliases"

# Portal root favicons
for app in frontend-admin frontend-customer; do
  cp -a "$SRC/favicon.svg" "$ROOT/$app/public/favicon.svg"
  cp -a "$SRC/favicon.ico" "$ROOT/$app/public/favicon.ico"
  cp -a "$SRC/apple-touch-icon-180.png" "$ROOT/$app/public/apple-touch-icon-180.png"
  cp -a "$SRC/app-icon-512.png" "$ROOT/$app/public/app-icon-512.png"
  echo "synced $app public favicons"
done

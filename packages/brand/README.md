# Kevantic Cyber Security — Production Brand Kit v1.1

This package locks the approved Kevantic visual identity into reusable vector assets.

## Important

The `KEVANTIC` wordmark is **not live SVG text**. Its custom approved silhouette was
vectorized from the supplied reference artwork and is stored as fixed SVG path geometry.

That means Windows, Linux, Chrome, Edge, Docker containers, the public website,
the MSSP Admin Dashboard, and the Customer Dashboard will all render the same wordmark
without relying on an installed font.

`CYBER SECURITY` is also converted to vector outlines.

## Canonical assets

- `kevantic-horizontal.svg` — **PRIMARY MASTER**; transparent background.
  Use for public website navigation, dashboard expanded navigation, and login pages.
- `kevantic-horizontal-dark.svg` — same lockup on official `#0B132B` canvas.
- `kevantic-wordmark.svg` — KEVANTIC + CYBER SECURITY without shield.
- `kevantic-mark.svg` — shield only; use for collapsed sidebars and app anchors.
- `favicon.svg` — optimized small-format shield on Midnight Obsidian.
- `favicon.ico`, `favicon-16.png`, `favicon-32.png` — compatibility fallbacks.
- `apple-touch-icon-180.png` — Apple touch icon.
- `app-icon-512.png` — high-resolution app/PWA icon.
- `kevantic-og-1200x630.png` — social/OpenGraph preview.
- `kevantic-brand.css` — shared brand color tokens and safe sizing helpers.
- `brand-manifest.json` — machine-readable asset policy.
- `CURSOR_APPLY_KEVANTIC_BRAND.md` — paste into Cursor Agent.

## Approved colors

- Midnight Obsidian: `#0B132B`
- Cosmic Platinum: `#D6E2E9`
- Steel Cyber Blue: `#3A506B`
- Network Blue: `#79A9D1`
- Display Cyber Blue: `#5F86AE`

## Usage

### Public website

```html
<a href="/" aria-label="Kevantic Cyber Security">
  <img
    src="/brand/kevantic-horizontal.svg"
    alt="Kevantic Cyber Security"
    class="kevantic-brand-logo"
  />
</a>
```

### Expanded Admin / Customer navigation

Use `kevantic-horizontal.svg`.

### Collapsed Admin / Customer navigation

Use `kevantic-mark.svg`.

### Favicon

```html
<link rel="icon" type="image/svg+xml" href="/brand/favicon.svg">
<link rel="icon" type="image/x-icon" href="/brand/favicon.ico">
<link rel="apple-touch-icon" href="/brand/apple-touch-icon-180.png">
```

## Never do this

```html
<!-- WRONG: this changes the logo when fonts/CSS change -->
<div class="logo">
  <img src="shield.svg">
  <span>KEVANTIC</span>
</div>
```

Do not rebuild the corporate wordmark with a web font.

## Recommended deployment model

If all three applications live in one monorepo, keep a single canonical source directory,
for example:

```text
packages/brand/
```

and copy/package it into each application's public assets during build.

If the applications are in separate repositories, copy this **unchanged versioned kit**
into each repository and verify the SHA-256 checksums in `SHA256SUMS.txt`.

## Source note

The original Illustrator/Figma/vector source was not supplied. Therefore the approved
custom `KEVANTIC` silhouette in this kit is a clean vector trace of the supplied raster
reference. From this release onward, treat `kevantic-horizontal.svg` as the master source
instead of recreating the logo from the raster image.


## v1.1 correction

The `CYBER SECURITY` subline in the primary horizontal lockup has been enlarged
approximately **2× in actual letter height** for reliable navigation/header rendering.
Its tracking was tightened so the subline remains aligned beneath the custom KEVANTIC
wordmark. The custom KEVANTIC path geometry and shield are unchanged.

The display subline uses `#6F9CC8` for improved legibility against Midnight Obsidian.

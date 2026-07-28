# MSSP Admin + Customer — Enterprise SOC-Glow Theme

Status: **Phase 1 tokens + Phase 2 dashboard re-skin applied**  
Surfaces: `frontend-admin` and `frontend-customer`

## Exact palette

| Token | Hex | Role |
|---|---|---|
| `--soc-canvas` | `#0B0F17` | App + sidebar background |
| `--soc-surface` | `#151C28` | Cards / containers |
| `--soc-surface-accent` | `#222F43` | 1px borders / dividers |
| `--soc-surface-hover` | `#1C2638` | Table / interactive hover |
| `--soc-accent` | `#00F0FF` | Cyber cyan primary |
| `--soc-accent-glow` | `#38BDF8` | Soft cyan alternate |
| Critical / High / Medium / Low | `#FF3B30` / `#FF9500` / `#FFCC00` / `#30D158` | Severity |

## Phase 2 deliverables

- Glow KPI cards (`GlowStatCard`) with trend badges
- SVG `SeverityDonut` replacing severity tables
- Solid severity pills (`SeverityPill`)
- Mono IDs/timestamps; row hover `#1C2638` + cyan inset
- Admin header: tenant switcher + engine status ribbon
- Customer header: tenant chip + engine status ribbon

TypeScript: both frontends `tsc -b` exit 0.

# Kevantic Sales Cloud (internal)

**URL:** `http://192.168.0.201:8090/` · version **1.4.0**  
**Login:** `kevantic-billing/data/OPERATOR_CREDS.txt` (do not commit)

Salesforce Lightning–style sales desk on top of the existing quote + GST invoice engine.

## What you see

- Dark slate sidebar, Inter typography, Salesforce blue actions
- **+ New Lead** modal (first/last name, company, source, budget, owner)
- Lead list filters, record banner, chevron path, **Convert Lead** modal → Account + Contact + Opportunity
- Opportunity Kanban with drag-and-drop stages
- Create Quote from Opportunity; Accept Quote → Closed Won + tax invoice when linked
- Dashboard: pipeline, weighted forecast, AR aging, quick actions

Sample rows are prefixed **TEST —**. Own Compose — does **not** touch Admin `:3000` / Customer `:3001`.

Architecture: `docs/CRM_ARCHITECTURE.md`

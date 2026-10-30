# Kevantic Sales CRM — architecture (Salesforce-style)

**Runtime:** same stack as quoting — `http://192.168.0.201:8090/` · own Compose · does **not** touch Admin `:3000` / Customer `:3001`.  
**Rule:** Quotes and Invoices stay the financial engine. CRM owns the sales cycle *around* them.

## What already exists (audit)

| Salesforce idea | Current table / route | Status |
|---|---|---|
| Account | `parties` + `/api/parties` | Keep. Rename in UI only to **Accounts**. |
| Quote | `quotes` + `/api/quotes` | Keep. Already has `opportunity_id`. |
| Invoice / Payment | `invoices`, `payments` + `/api/invoices` | Keep. Already has `opportunity_id`. |
| Product catalog | `catalog_items` | Keep. Any supplier / any SKU. |
| Lead | `leads` + `/api/crm/leads` | Extend statuses + conversion. |
| Contact | `contacts` | Extend (account 360 view). |
| Opportunity | `opportunities` | Align stages to classic pipeline. |
| Activity | `activities` | Extend to Account + Contact. |
| Owner | `salespeople` | BDC / BDE / manager assignment. |
| OEM / distributor price | `supplier_prices` | Channel-partner extra (not core Salesforce). |

Bidirectional money link already intended:

`Lead → Opportunity → Quote → Invoice → Payment`

---

## 1. Database schema plan

### Keep (financial core — do not rewrite)

- `parties` → **Account**
- `quotes`, `quote_lines` (`opportunity_id`, `vendor_name`)
- `invoices`, `invoice_lines`, `payments` (`opportunity_id`)
- `catalog_items`

### CRM tables

| Table | Purpose | Key links |
|---|---|---|
| `salespeople` | BDC / BDE / manager | Assigned on Lead + Opportunity |
| `leads` | First inbound interest | Optional `party_id` after convert; `salesperson_id` |
| `contacts` | People at an Account | `party_id` |
| `opportunities` | One customer **requirement** / deal | `party_id`, `contact_id`, `lead_id`, `salesperson_id` |
| `activities` | Timeline | `lead_id` and/or `opportunity_id` and/or `party_id` and/or `contact_id` |
| `supplier_prices` | OEM / distributor cost → sell price | `opportunity_id` (channel resale) |

### Lead statuses (Salesforce)

`new` → `contacted` → `qualified` → `converted`  
or `unqualified`

**Conversion (automated):** Qualified/Convert creates Account (`parties`) if needed + Contact + Opportunity, sets Lead = `converted`.

### Opportunity stages (Kanban)

| Stage | Default win % |
|---|---|
| `prospecting` | 10 |
| `needs_analysis` | 25 |
| `proposal` | 50 |
| `negotiation` | 75 |
| `closed_won` | 100 |
| `closed_lost` | 0 |

**Weighted forecast** = `amount_expected × probability / 100`.

### Money hooks (existing engines)

1. Opportunity → **Generate Quote** (prefill Account, owner, lines from catalog and/or chosen supplier prices).
2. Quote **Accepted** → Opportunity → `closed_won`; offer Invoice via existing `/api/invoices/from-quote/{id}`.
3. Tax Invoice issued / Payment collected → fulfillment fields; Account stays for the next requirement.

---

## 2. Component & API route mapping

### API (new / extend under `/api/crm`)

| Area | Routes |
|---|---|
| Team | `GET/POST /team`, `PATCH /team/{id}` |
| Leads | `GET/POST /leads`, `GET/PATCH /leads/{id}`, `POST /leads/{id}/convert`, activities |
| Opportunities | `GET/POST /opportunities`, `GET/PATCH /{id}`, supplier-prices, `customer-quote`, activities |
| Accounts 360 | Extend parties: contacts + open/closed opps + quotes + invoices + activities |
| Analytics | Extend `/api/crm/summary` + dashboard: pipeline, weighted forecast, win/loss, AR |

Existing (unchanged contracts): `/api/quotes`, `/api/invoices`, `/api/parties`, `/api/catalog`.

### UI tabs

| Tab | Job |
|---|---|
| Dashboard | Pipeline, weighted forecast, open leads, AR |
| Leads | Capture, assign BDC/BDE, qualify, convert |
| Pipeline | Kanban by stage; open deal drawer |
| Accounts | Party 360 (contacts, deals, quotes, invoices, timeline) |
| Team | Sales people |
| New quote / Quotes / Invoices / Catalog | Existing financial screens |

---

## 3. Build sequence

1. **Step 1 (this pass):** Schema alignment + Lead → Account + Contact + Opportunity conversion.
2. **Step 2:** Opportunity Kanban + deal properties + weighted forecast.
3. **Step 3:** Generate Quote from Opportunity; Accept Quote → Closed Won → Invoice.
4. **Step 4:** Full activity timeline on Account / Contact / Opportunity.
5. **Step 5:** Analytics dashboard + test sales team / sample customers.

---

## Naming in the product

UI says **Account**, **Contact**, **Lead**, **Opportunity**.  
Database keeps `parties` for Accounts so the GST invoice engine does not break.

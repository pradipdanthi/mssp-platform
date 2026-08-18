# Kevantic NikTiar™ Pitch Deck — NotebookLM Source Document

**Document type:** Slide deck source for Google NotebookLM  
**Product:** Kevantic NikTiar™ Sovereign Cyber Defense Platform  
**Operator:** Kevantic Cyber Security Private Limited  
**Audience:** Enterprise buyers, CISOs, IT leaders, regulated industries  
**Slide count:** 10  
**Generation intent:** Each `## SLIDE` block maps to one presentation slide. Use headings as slide titles; bullets as on-slide copy; *Speaker notes* and *Visual cues* guide layout and narration.

---

## SLIDE 1: Title & Vision — Kevantic NikTiar™ Sovereign Cyber Defense

### Headline
**Enterprise-Grade Cybersecurity. Autonomous Threat Detection. Guaranteed Hybrid Sovereignty.**

### Subheadline
The Kevantic NikTiar™ platform is a hybrid MSSP stack that keeps **raw telemetry on your premises** while a **24/7 Cloud SOC** investigates, contains, and proves compliance—without shipping your entire log estate to a vendor cloud.

### Key bullets
- **Managed service, not a DIY license** — Kevantic analysts own detection, response, and customer-facing outcomes
- **Hybrid sovereignty by design** — you retain raw logs locally; we hunt on encrypted high-priority alerts
- **One platform, four tiers** — Bronze through Platinum on a single control plane with dynamic licensing
- **NikTiar™ engine family** — unified capability branding across endpoint, network, vulnerability, SOAR, and DFIR
- **Built for regulated and multi-site estates** — PCI-DSS, ISO 27001, and HIPAA scorecards in the customer portal

### Tagline
*You keep the logs. We hunt, contain, and prove it.*

### Visual cues
- Full-bleed dark cyber aesthetic with Kevantic wordmark
- Hero split: Edge Node (on-prem) ↔ encrypted uplink ↔ Cloud SOC cluster
- Status chips: **SOC Online · HA 3-Node · TLS Encrypted · 99.95% Uptime**

### Speaker notes
Open with the buyer pain: they need enterprise SOC outcomes but cannot accept full cloud log lock-in or run another security tool themselves. Position NikTiar as sovereign cyber defense—a productized MSSP platform, not a SIEM SKU.

---

## SLIDE 2: The Modern MSSP Dilemma — Cloud Tax, Bandwidth Overkill, Data Residency

### Headline
**Traditional cloud-first MSSP models force an impossible tradeoff.**

### Problem statement
Enterprises are told to "move security to the cloud." In practice, that means paying to ship, store, and re-process **100% of raw telemetry**—even when policy, bandwidth, or sovereignty rules say most of it must stay local.

### Key bullets — Cloud Tax
- **Per-GB ingest and retention fees** inflate TCO as endpoint, network, and cloud workloads grow
- **Vendor data-lake lock-in** — long-term log history becomes a recurring tax, not a strategic asset
- **Duplicate processing** — local collectors plus cloud re-indexing pay twice for the same signal

### Key bullets — Bandwidth Overkill
- **WAN saturation** from shipping full packet captures and verbose logs off-site
- **Latency and blind spots** when remote sites throttle or drop telemetry during peak load
- **Forensic replay suffers** when raw history lives only in a distant vendor region

### Key bullets — Data Residency
- **Regulators and boards** increasingly require proof that sensitive logs never leave jurisdiction
- **"Logs cannot leave our DC"** is a deal-breaker for cloud-only SIEM/MSSP proposals
- **Hybrid estates** (on-prem + AWS/Azure/GCP) need one SOC model—not three incompatible stacks

### Impact callout
**Buyers want managed outcomes without surrendering data sovereignty or budget to a cloud tax.**

### Visual cues
- Three-column pain layout: **Cloud Tax | Bandwidth | Residency**
- Red/amber warning metrics: rising ingest cost curve, WAN utilization spike, map pins for data-sovereignty zones

### Speaker notes
Name the dilemma plainly. Do not attack competitors by name—attack the **model**: full-cloud ingest as default. Set up Slide 3 as the architectural answer.

---

## SLIDE 3: The Kevantic NikTiar™ Paradigm Shift — Sovereign Edge Ingestion & Zero-Tax SOC

### Headline
**Stop paying to ship what you should keep. Start paying for outcomes.**

### Paradigm shift
Kevantic inverts the cloud-first MSSP model: **ingest and retain at the edge**, forward **only scored, encrypted high-priority alerts and metadata** to the Cloud SOC.

### Key bullets — Sovereign Edge Ingestion
- **Kevantic NikTiar™ Edge Node** processes telemetry locally—endpoint, network, and scan data stay in your datacenter or VPC
- **365+ day retention** without a vendor data-lake tax; raw history available for on-site retrospective hunts
- **Outbound-only secure channel** (TLS/mTLS)—no inbound firewall holes required for day-to-day operations
- **Single ISO, multiple deployment modes** — on-prem, cloud VPC, or hybrid under one appliance image

### Key bullets — Zero-Tax SOC
- **Cloud SOC analyzes signal, not noise** — high-fidelity alerts and metadata, not full log firehoses
- **~0% raw log egress** in flagship on-prem appliance mode—SOC visibility without log exfiltration
- **24/7 analyst-led response** with AI-assisted correlation inside Kevantic's managed SOC (not customer-operated AI)
- **Dynamic licensing** — upgrade DeepSight NDR, Apex SOAR, or Platinum SLAs from the control plane without rip-and-replace

### Proof points
- Machine-speed correlation with **human-accountable containment**
- Target **MTTC ~800ms** under approved playbooks (Gold/Platinum)
- **Multi-node HA Cloud SOC** for investigation, casework, and orchestration

### Visual cues
- Before/after diagram: *Old model* (100% logs → vendor cloud) vs *NikTiar model* (raw local, alerts → SOC)
- Green check on **Zero-Tax Data Path**

### Speaker notes
This is the strategic wedge. Sovereignty is not a feature flag—it is the default operating model for regulated and bandwidth-constrained buyers.

---

## SLIDE 4: 3-Tier Sovereign Architecture — Edge Node, Cloud SOC, Control Plane

### Headline
**Three tiers. One sovereign operating model.**

### Architecture overview
```text
┌──────────── Hybrid Edge Tier ────────────┐
│  NikTiar™ Edge Node (on-prem / VPC)     │
│  Core · DeepSight NDR · Aegis Scanning   │
│  Raw logs & packets STAY LOCAL           │
└──────────────────┬───────────────────────┘
                   │ TLS — metadata + critical alerts only
                   ▼
┌──────────── Cloud SOC Tier ──────────────┐
│  24/7 multi-node operations core         │
│  Apex SOAR · Spectre DFIR · case mgmt    │
└──────────────────┬───────────────────────┘
                   │ unified APIs & licensing
                   ▼
┌──────────── Control Plane Tier ──────────┐
│  Admin + Customer portals                │
│  Compliance scorecards · entitlements    │
└──────────────────────────────────────────┘
```

### Tier 1 — Hybrid Edge (Kevantic NikTiar™ Edge Node)
- Local ingestion via **NikTiar™ Core**, **DeepSight NDR**, and **Aegis Scanning**
- Raw telemetry, full packets (Gold/Platinum), and forensic artifacts remain on-site
- Deployment options: **optional single node · included Edge Node (Silver) · HA pair (Gold) · dedicated cluster (Platinum)**
- Network posture: bootstrap patch window → **locked** steady state (SOC channel only)

### Tier 2 — Cloud SOC (Kevantic NikTiar™ Cloud SOC)
- Receives **encrypted high-priority alerts** without raw log lock-in
- **NikTiar™ Apex SOAR** triggers playbooks and containment under analyst approval
- **NikTiar™ Spectre DFIR** for live memory forensics and process-tree investigation
- Centralized casework—**no on-prem ticketing UI** on the appliance

### Tier 3 — Control Plane (Kevantic NikTiar™ Control Plane)
- Unified **Client Portal** and **Administrative Console**
- **Dynamic JWS license keys** enforce Bronze–Platinum capabilities per tenant
- Real-time **PCI-DSS, ISO 27001, HIPAA** compliance scorecards
- Multi-tenant isolation with entitlement-driven engine provisioning

### Deployment modes (same stack)
| Mode | Summary |
|------|---------|
| Cloud | Direct cloud agent streaming to managed SOC |
| Cloud + Edge | Cloud workloads + edge metadata filter |
| On-prem | Agents to Cloud SOC without edge box |
| **On-prem + Edge (flagship)** | **100% raw logs local; metadata/alerts to SOC** |

### Visual cues
- Vertical stack diagram with three labeled layers and animated data-flow arrows
- Color code: **amber = raw stays local · cyan = metadata to SOC**

### Speaker notes
Emphasize separation of concerns: edge retains, SOC responds, control plane governs and reports. This maps cleanly to buyer org charts (IT owns edge, Kevantic owns SOC, executives use portal).

---

## SLIDE 5: Proprietary Security Engine Family — NikTiar™ Core, DeepSight NDR, Aegis, Apex SOAR, Spectre DFIR

### Headline
**One integrated engine family. Productized capabilities—not a patchwork of vendor consoles.**

### Engine catalog

| NikTiar™ Capability | Function | Buyer-facing value |
|---------------------|----------|-------------------|
| **NikTiar™ Core** | Endpoint & log telemetry pipeline | 24/7 SIEM-grade monitoring; agents on servers and endpoints; local normalization at the edge |
| **NikTiar™ DeepSight NDR** | Network detection & traffic analysis | Lateral movement, beaconing, and IDS/NTA visibility; packet-level inspection at Gold/Platinum |
| **NikTiar™ Aegis** | Vulnerability assessment | Prioritized CVE exposure; scan cadence scales by tier (monthly → continuous) |
| **NikTiar™ Apex SOAR** | Security automation & case orchestration | Playbooks, enrichment, and containment (`ISOLATE_HOST`, process kill, hash block) with SOC approval |
| **NikTiar™ Spectre DFIR** | Endpoint forensics & live response | Process trees, memory forensics, deception/canary support; deep investigation without customer raw-data exposure |

### Additional platform modules (tier/add-on)
- **NikTiar™ Threat Intelligence** — IOC sync, live feed matching, custom feeds at Platinum
- **Managed Detection umbrella** — normalized, tenant-scoped alerts in the customer portal (plain English, no engine jargon)

### Integration principle
- Engines execute **behind the Kevantic brand**—customers and executives see **NikTiar™ labels only** in portals
- All sources normalize to **tenant-scoped records**: alerts, incidents, assets, vulnerabilities, reports
- **Fail-closed tenant mapping** — no cross-customer data leakage

### Visual cues
- Pentagon or hub-spoke diagram with **NikTiar™** at center and five engine nodes
- Icon per engine; short one-line value under each

### Speaker notes
This slide is the "what you get" catalog. Stress that buyers subscribe to **outcomes and modules**, not a bag of open-source tools to operate themselves.

---

## SLIDE 6: Productized Subscription Tiers — Bronze, Silver, Gold, Platinum Comparison Matrix

### Headline
**Four subscription tiers. One hybrid control plane. Upgrade without platform swap.**

### Tier positioning

| Tier | Package name | Target buyer | One-line promise |
|------|--------------|--------------|------------------|
| **Bronze** | Core SIEM | SMB compliance | Foundational telemetry + monthly Aegis scans + email IR notifications |
| **Silver** | Advanced Sec | Mid-market hybrid | Weekly Aegis scans, daily IOC sync, standard triage, **Edge Node included** |
| **Gold** | Enterprise NDR | Enterprise networks | Daily scans, DeepSight NDR, live Apex SOAR, guided remediation, **HA appliance pair** |
| **Platinum** | Full Autonomous SOC | Mission-critical / financial | Continuous Aegis, 15-min SLA + automated containment, Spectre live memory DFIR, **dedicated cluster** |

### Feature comparison matrix

| Feature / Capability | Bronze | Silver | Gold | Platinum |
|----------------------|--------|--------|------|----------|
| **Target infrastructure** | SMB compliance | Mid-market hybrid | Enterprise networks | Mission-critical / financial |
| **Log ingestion & SIEM** | NikTiar™ Core | NikTiar™ Core | NikTiar™ Core | NikTiar™ Core |
| **Vulnerability scans (Aegis)** | Monthly | Weekly | Daily automated | Continuous + remediation |
| **Network detection (NDR)** | — | — | DeepSight NDR | DeepSight NDR (full packet) |
| **Threat intelligence** | Static signatures | Daily IOC sync | Live Apex SOAR stream | Custom threat feeds |
| **Incident response** | Email notifications | Standard triage | Guided remediation | **15-min SLA + Apex SOAR containment** |
| **DFIR forensics (Spectre)** | Standard logs | Endpoint telemetry | Spectre triage | **Live memory & process tree** |
| **NikTiar™ Edge Node** | Optional | **Included** | **Included (HA pair)** | **Dedicated high-throughput cluster** |

### Commercial flexibility
- **Dynamic licensing** — provision DeepSight NDR, HA Edge Nodes, or Platinum SLAs from the control plane
- **Start Bronze or Silver** — grow into Gold/Platinum as risk and residency requirements increase
- **Same customer portal and service menu** across all tiers

### Visual cues
- Four tier cards (Bronze/Silver light, Gold/Platinum dark) above a comparison table
- Ribbon on Gold: **"Most chosen"** · Platinum: **"Flagship"**

### Speaker notes
Walk one row of the matrix aloud (e.g., NDR and Edge Node progression). Ask the buyer which column matches their estate size and regulatory posture.

---

## SLIDE 7: Incident Lifecycle & Automated Containment Workflow

### Headline
**From signal to contained incident—in minutes, with humans accountable.**

### Lifecycle stages

| Stage | What happens | Who owns it |
|-------|--------------|-------------|
| **1. Detect** | Core, DeepSight NDR, or Aegis raises a scored alert at the edge or cloud path | NikTiar™ engines + Kevantic SOC |
| **2. Correlate** | AI links related signals into attack chains; analysts cut through single-event noise | Kevantic SOC (AI-assisted) |
| **3. Triage** | 24/7 analysts validate severity, tenant scope, and business impact | Kevantic SOC |
| **4. Investigate** | Case opened in Cloud SOC; Spectre DFIR process trees and forensics where licensed | Kevantic SOC |
| **5. Contain** | Apex SOAR playbooks execute approved actions: `ISOLATE_HOST`, kill process, block hash | Analyst-approved automation |
| **6. Communicate** | Plain-English summary, timeline, and recommendations published to **Customer Portal** | Kevantic SOC → customer leadership |
| **7. Close & learn** | Audit-ready timeline, monthly reporting, compliance scorecard updates | Control Plane |

### Automated containment workflow
```text
High-priority alert (edge or cloud)
        → Encrypted forward to Cloud SOC
        → Apex SOAR playbook armed
        → Analyst approval gate (policy-based; auto at Platinum SLA)
        → Active response on endpoint/network
        → Verification + customer portal update
```

### Containment actions (approved playbooks)
- **Host isolation** — `ISOLATE_HOST` via OS-native controls
- **Process termination** — stop malicious process by identity
- **Hash blocking** — propagate block across connected endpoints
- **Target MTTC** — **~800 milliseconds** under approved Gold/Platinum playbooks (vs. hours in ticket-queue models)

### Customer safety rules
- Customers see **plain-English status only**—no raw logs, packet captures, or internal SOC notes
- AI **drafts**; analysts **validate** before anything reaches the portal
- Containment never runs "dark"—every action is logged and attributable

### Visual cues
- Horizontal lifecycle chevron: Detect → Correlate → Triage → Investigate → Contain → Communicate → Close
- Side panel mock: SOC console + portal handoff

### Speaker notes
Stress the hybrid value: edge retains forensic depth locally; SOC executes fast containment; executives get clarity without technical noise.

---

## SLIDE 8: Control Plane Intelligence & Compliance Scorecards (PCI-DSS, ISO 27001, HIPAA)

### Headline
**One portal for executives, auditors, and IT—real-time posture, not quarterly slide decks.**

### Control plane capabilities
- **Client Portal** — alerts, incidents, appliance health, vulnerabilities, reports, service upgrade requests
- **Administrative Console** — tenant onboarding, entitlements, activation tokens, cross-tenant SOC operations
- **AI-assisted summaries** — business impact and recommended actions in plain English (analyst-reviewed)
- **Dynamic service provisioning** — request NDR, HA appliances, or tier upgrades in one click

### Compliance scorecards

| Framework | What the portal tracks | Buyer outcome |
|-----------|------------------------|---------------|
| **PCI-DSS** | Logging, monitoring, access, and incident-response control alignment | Auditor-ready evidence for cardholder environments |
| **ISO 27001** | ISMS-aligned monitoring, incident handling, and continuous improvement metrics | Structured proof for certification and surveillance audits |
| **HIPAA** | Security incident procedures, access monitoring, and risk-management visibility | Healthcare and BAAs get defensible, ongoing reporting |

### Continuous compliance add-on (CaaS)
- **CIS benchmark readiness scoring** for Windows and Linux estates
- Percentage-style **compliance readiness ring** in the customer portal
- Bridges technical telemetry to **board and auditor language**

### Reporting & accountability
- Monthly **published reports** with executive summaries
- Incident timelines exportable for leadership and audit conversations
- **Tenant-isolated** views—Customer A never sees Customer B data (404 on cross-tenant access)

### Visual cues
- Split screen: compliance scorecard (78% readiness ring) + incident timeline + upgrade request button
- Framework badges: PCI-DSS · ISO 27001 · HIPAA

### Speaker notes
This slide speaks to CISO + CFO + compliance officer. The control plane is how Kevantic **proves** the service between audits—not just during them.

---

## SLIDE 9: Competitive Advantages & Total Cost of Ownership (TCO)

### Headline
**Lower long-term TCO by design—not by discounting outcomes.**

### Competitive advantages

| Advantage | Kevantic NikTiar™ | Typical cloud-first MSSP / SIEM |
|-----------|-------------------|----------------------------------|
| **Data sovereignty** | Raw logs stay local at the edge; ~0% raw egress in flagship mode | Full ingest to vendor cloud required |
| **Commercial model** | Managed MSSP subscription with tiered outcomes | DIY platform + SIEM tax + separate MDR upsell |
| **Architecture** | 3-tier edge + SOC + control plane on one license plane | Disconnected agents, lakes, and SOAR tools |
| **Upgrade path** | Bronze → Platinum without rip-and-replace | New SKUs, migrations, professional services |
| **Customer experience** | Branded NikTiar™ portal; plain-English, leadership-ready | Analyst portals or raw SIEM consoles exposed |
| **Containment** | Sub-second MTTC path with analyst-approved Apex SOAR | Manual ticket queues and delayed response |
| **Compliance** | Live PCI / ISO / HIPAA scorecards | Periodic manual compliance projects |
| **Hybrid estates** | Four deployment modes under one SOC | Separate products for cloud vs on-prem |

### TCO levers (where savings compound)
- **Eliminate cloud ingest tax** on terabytes that never need to leave the datacenter
- **Reduce WAN costs** — metadata/alerts only over TLS, not full packet/log firehoses
- **Avoid duplicate tooling** — one engine family and one portal vs. SIEM + NDR + VM + SOAR vendors
- **Right-size by tier** — start Silver; add Gold NDR when network risk justifies it
- **Operational offload** — no customer SOC headcount to hire, train, and retain for 24/7 coverage
- **Audit efficiency** — continuous scorecards reduce expensive pre-audit fire drills

### TCO summary statement
**Pay for managed detection and response—not for shipping your entire log history to someone else's lake.**

### Visual cues
- TCO iceberg: visible subscription vs. hidden ingest/storage/bandwidth costs (competitor model submerged)
- Checklist of six advantages with green ticks

### Speaker notes
Quantify qualitatively if the buyer shares estate size: more endpoints and longer retention amplify the cloud-tax delta. Offer a mapped quote (Slide 10 CTA).

---

## SLIDE 10: Call to Action — 14-Day Risk-Free Edge Node Deployment

### Headline
**Prove sovereign cyber defense in your environment—in 14 days, risk-free.**

### Offer summary
Deploy a **Kevantic NikTiar™ Edge Node** on your LAN or VPC. Experience local log retention, encrypted alert forwarding, and Kevantic SOC triage—before you commit to a full-tier subscription.

### What's included in the 14-day deployment
- **Edge Node provisioning** — single-node pilot (upgrade path to HA pair or Platinum cluster documented upfront)
- **NikTiar™ Core telemetry** — endpoint and server agent onboarding assistance
- **Secure SOC channel** — TLS/mTLS outbound-only connectivity to Kevantic Cloud SOC
- **Live control plane access** — Client Portal preview with alert and compliance views
- **SOC touchpoint** — analyst review of high-priority signals during the pilot window
- **Exit clarity** — keep sovereignty guarantees documented; no raw-log egress during pilot

### Ideal pilot profiles
- **"Logs cannot leave our DC"** — regulated, healthcare, finance, government contractors
- **Multi-site hybrid** — on-prem plus cloud workloads under one customer tenant
- **Lean IT** — need 24/7 eyes without building an internal SOC
- **Gold/Platinum evaluation** — testing DeepSight NDR and Apex SOAR containment paths

### Next steps

| Step | Action |
|------|--------|
| **1** | Share estate size, residency constraints, and target tier (Bronze–Platinum) |
| **2** | Kevantic maps Edge Node sizing: single node, HA pair, or dedicated cluster |
| **3** | Schedule 14-day risk-free deployment and activation token handoff |
| **4** | Day 14 review: telemetry health, sample incidents, compliance scorecard walkthrough |
| **5** | Convert to production tier with dynamic licensing—or exit with full audit trail |

### Contact
- **Email:** sales@kevantic.com  
- **Web:** Request NikTiar™ Edge Node Demo (Kevantic corporate site)  
- **Existing clients:** Client Portal Access for live dashboard and service menu

### Closing line
**Hybrid sovereignty is not a roadmap slide—it is deployable in fourteen days.**

### Visual cues
- Bold CTA button treatment: **Start 14-Day Edge Node Pilot**
- Calendar timeline: Day 0 Deploy → Day 7 First incidents → Day 14 Executive readout
- Kevantic logo + NikTiar™ wordmark lockup

### Speaker notes
End with urgency and low friction. The pilot de-risks the residency conversation—the buyer proves local retention and SOC response before procurement finalizes tier and cluster sizing.

---

## Appendix: NotebookLM Generation Hints

**Recommended deck style:** Enterprise cybersecurity pitch; dark background; cyan/teal accents; minimal text per slide (max 5 bullets); one diagram per architecture/workflow slide.

**Brand terms to preserve exactly:** Kevantic, NikTiar™, NikTiar™ Core, NikTiar™ DeepSight NDR, NikTiar™ Aegis, NikTiar™ Apex SOAR, NikTiar™ Spectre DFIR, Edge Node, Cloud SOC, Control Plane.

**Do not use on customer-facing slides:** upstream open-source engine product names (Wazuh, Suricata, Zeek, etc.)—legal attributions belong in documentation only.

**Suggested narration arc:** Pain (Slide 2) → Paradigm (Slide 3) → Architecture (Slide 4) → Engines (Slide 5) → Commercial tiers (Slide 6) → Operations proof (Slides 7–8) → Business case (Slide 9) → Close (Slide 10).

---

*End of NotebookLM source document — 10 slides.*

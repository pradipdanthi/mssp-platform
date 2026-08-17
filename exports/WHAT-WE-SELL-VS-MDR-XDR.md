# What we sell vs MDR / XDR

**One-page positioning sheet** · Kestrel / Kevantic MSSP Control Plane  
**Audience:** customer demo, sales call, CISO Q&A  
**Rule:** sell outcomes honestly — AI assists; analysts decide; customers see only approved summaries.

---

## One-line position

We deliver **Managed Detection & Response (MDR)** with a **co-managed customer portal**, plus optional **MXDR add-ons** (endpoint containment, network, identity, vuln, TI, EASM). We are **not** a fully autonomous AI SOC and **not** a managed firewall vendor.

---

## Market labels — when to use them

| Phrase | Use it? | How to say it |
|--------|---------|----------------|
| **MSSP / SOC platform** | Yes | “We run a multi-tenant SOC with Admin + Customer portals.” |
| **MDR** | Yes — **core** | “We monitor, detect, investigate, and guide/contain response.” |
| **Co-managed MDR** | Yes — **best phrase** | “We investigate and act; your IT gets clear actions in the portal.” |
| **MXDR / emerging XDR** | Yes — **precise** | “We correlate endpoint + network + cases and can contain hosts.” |
| **XDR (full platform replacement)** | Soft only | “Multi-signal direction — not ‘we replace CrowdStrike overnight’.” |
| **Fully autonomous AI SOC** | **No** | AI drafts summaries; humans approve visibility and response. |
| **Managed firewall** | **No** | Firewall events can feed detection; we don’t sell managed FW. |
| **Managed M365 / ITDR** | Soft yes | Workflow exists; live Entra Graph is the upgrade step. |

---

## Your 10 offerings → market language

| # | What we sell | Market bucket | Role in MDR / XDR story |
|---|--------------|---------------|-------------------------|
| 1 | Log & Event Monitoring | SIEM / telemetry | **MDR core** — continuous detection |
| 2 | Incident Response & Casework | SOC casework | **MDR core** — investigate & track |
| 3 | Security Automation & Containment | EDR / active response | **MXDR** — isolate / kill / block |
| 4 | Vulnerability Management | VMaaS | Add-on — patch priority, not “incidents for every CVE” |
| 5 | Continuous Compliance | CaaS | Add-on — hardening scorecards |
| 6 | Network Detection & Response | NDR | **XDR signal** — network layer |
| 7 | Threat Intelligence & Enrichment | TI | Enrich alerts / cases |
| 8 | Endpoint Forensics & Deception | DFIR / hunt | Deep investigation |
| 9 | External Attack Surface | EASM | Outside-in exposure |
| 10 | Cloud & Identity Protection | ITDR | Identity / SaaS layer (connect Graph for full live) |

**Commercial default:** new customer starts with **1 + 2 (core MDR)**. Add-ons are entitlement / consulting activated.

---

## MDR pipeline (what buyers expect) → how we deliver

```
Customer estate (agents / appliance / sensors)
        ↓
Detect (SIEM rules, NDR, scanners)
        ↓
Ingest & normalize (our control plane = system of record)
        ↓
AI assist (plain-English draft — not auto-approval)
        ↓
Human SOC (Admin portal: triage, assign, contain)
        ↓
Customer portal (approved summaries + actions only)
        ↓
Remediation (SOC containment + customer IT fixes)
```

| Buyer expectation | We have it? | Proof in product |
|-------------------|-------------|------------------|
| Continuous monitoring | Yes | Agents + appliance forwarder + sensors |
| Detection | Yes | Alerts in Admin / Customer (when visible) |
| Investigation | Yes | Incidents, timeline, comments, TheHive path |
| Response | Yes (co-managed) | Isolate/kill model + recommendations |
| Customer outcomes | Yes | Portal — no raw SIEM dump |
| Autonomous AI remediation | No | Human-approved |

---

## HDL layer check (demo talking points)

| Layer in typical “AI MDR” diagram | Our status | One sentence for the room |
|-----------------------------------|------------|---------------------------|
| EDR | Strong | “Endpoint telemetry + containment.” |
| Firewall | Signal only | “We detect FW/network events; we don’t manage your firewall.” |
| Identity | Partial | “ITDR workflow ready; live M365 when Graph is connected.” |
| SIEM / XDR | Strong | “Our portal is the system of record across signals.” |
| Detection engine | Strong | “Rules + sensors + scanners behind adapters.” |
| AI SOC agent | Assistive | “AI drafts explainers; SOC owns the decision.” |
| Enrich / correlate / explain | Yes | “TI + cases + plain-English summaries.” |
| Human analyst | Required | “This is the product — not a black box.” |
| Notify customer | Growing | “Portal first; push channels optional.” |
| Remediate | Co-managed | “We can contain; IT completes the fix.” |

---

## 30-second pitch

> “We are an **MDR provider** with a co-managed portal. We detect and investigate around the clock, explain issues in plain English, and can contain endpoints when needed. Your team sees only approved summaries and clear actions — not raw logs or vendor consoles. Extra services — vulnerability, network, identity, attack surface — plug into the same portal as you grow.”

---

## Do / Don’t in the room

| Do | Don’t |
|----|-------|
| Say **MDR** and **co-managed** | Say **fully autonomous AI SOC** |
| Show Admin vs Customer split | Hand customers a Wazuh/TheHive login |
| Show one clean incident end-to-end | Show 50 open noise tickets |
| Admit identity/Graph and adapter honesty | Claim live Entra if Graph isn’t connected |
| Call containment **capability** | Isolate a host mid-demo without a plan |

---

## Maturity snapshot (internal)

**Cashflow baseline:** Level 3 — **Co-managed MDR / emerging MXDR**  
**Direction:** Advanced XDR + identity/cloud + continuous exposure (ITDR live Graph, deeper NDR, hunting).

---

*One page · use for demos · update when Graph ITDR or notification workers go fully live.*

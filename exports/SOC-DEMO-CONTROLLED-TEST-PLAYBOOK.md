# SOC controlled test — step-by-step runbook (all 10 services)

**Purpose:** For each service we sell, you **generate a controlled signal**, **find it in the portal**, and **work the ticket like a real SOC analyst**. Lab only — no malware, no unplanned host isolation.

**Control plane:** `http://192.168.0.201`  
**Admin SOC portal:** `:3000`  
**Customer portal:** `:3001`  
**Demo tenant (full catalog):** Alpha-Win-Corp — login `admin@alphawin.com`  
**Appliance contrast tenant:** Beta-Win-Corp — login `admin@betawin.com`  
**Admin SOC login:** `platform.admin@example.local` (lab password in validation.env)

**Helper script (fires detections / syncs):**

```bash
cd /opt/mssp-control
chmod +x scripts/soc_demo_fire_detection.sh
./scripts/soc_demo_fire_detection.sh --help
```

---

## Before you start (once per session)

1. Hard-refresh both portals (Ctrl+Shift+R).
2. Confirm health: `curl -fsS http://192.168.0.201:8000/health`
3. Power on lab VMs if they were stopped overnight: **104, 105, 108, 110** (Windows, Linux, MISP bridge, Velociraptor).
4. Log in **Admin :3000** as platform admin — keep this tab open.
5. Log in **Customer :3001** as `admin@alphawin.com` — second tab for “what the customer sees”.
6. On Admin **Dashboard**, note **Active Incidents** (should be 0 or 1 hero case from earlier rehearsal).

---

## The SOC loop (repeat after every detection)

Use this every time so the demo feels consistent:

| Step | Where (Admin) | What you do | What you say to the customer |
|------|---------------|-------------|------------------------------|
| 1 | **Alerts** | Find the new row (sort by time) | “Detection landed in seconds.” |
| 2 | **Alert detail** | Read severity, asset, technical summary | “Our analysts see full context; you don’t get raw logs.” |
| 3 | **Alert detail → Triage** | Set status, **Customer visible**, plain-English summary + recommended action → **Save** | “Nothing reaches you until we approve it.” |
| 4 | **Incidents** | Open linked case (auto if high/critical) | “A tracked case exists — not a spreadsheet.” |
| 5 | **Incident detail** | Assign analyst, set **In progress**, customer summary + **Customer action required** → **Save** | “Here is what we need from your IT.” |
| 6 | **Incident detail → Comments** | Add **internal** note + **customer** note | “Full audit trail.” |
| 7 | **Recommendations** | Create linked recommendation, tick **Customer visible** | “Clear fix list for IT.” |
| 8 | **Customer :3001** | Alerts / Incidents / Recommendations | “This is your view — no vendor consoles.” |
| 9 | (Later) **Incident detail** | **Resolved/Closed** + resolution note | “Case closed with evidence.” |

**Alert triage fields (Admin → Alerts → row → open):**

- Status: `triaged` or `incident_created`
- **Customer visible:** ON
- **Plain-English summary:** non-technical paragraph
- **Recommended action:** what IT must do
- Click **Save alert triage**

**Incident fields (Admin → Incidents → row → open):**

- Status: `in_progress`
- **Assigned to:** Demo SOC Analyst (or yourself)
- **Customer visible summary**
- **Customer action required**
- Click **Save incident triage**
- **Add comment** (internal vs customer visibility)

---

## Service 1 — Log & Event Monitoring

**What this service is:** 24/7 endpoint/server log monitoring → alerts in our portal.

### A. Generate the detection

**Option A — scripted (recommended for demo):**

```bash
cd /opt/mssp-control
./scripts/soc_demo_fire_detection.sh s01-powershell
```

**Option B — real endpoint (Windows lab VM 104, `192.168.0.214`):**  
RDP to the Windows lab as Administrator, then run **one** harmless command:

```powershell
powershell -NoProfile -Command "Write-Host 'SOC demo benign test'"
```

Or a controlled firewall rule (creates Netsh alert):

```powershell
netsh advfirewall firewall add rule name="SOC-DEMO-TEST-RULE" dir=in action=allow protocol=TCP localport=59999
```

Wait 30–60 seconds for Wazuh agent → Manager → (optional) webhook → control plane.

### B. Find it in the dashboard

1. Admin **Dashboard** — **Events monitored** / alert KPI should tick up (after refresh).
2. Admin **Alerts** — newest row: *PowerShell* or *Netsh*.
3. Filter tenant **Alpha-Win-Corp** if needed.

**Pass:** New alert row exists, severity **high** or **critical**, asset **WIN-BL72S84GDTF**.

### C. SOC analyst work

1. Open the alert.
2. Confirm **Wazuh rule**, **MITRE** (Execution / PowerShell if shown).
3. Run the **SOC loop** steps 1–3 (triage + customer visible + summary).
4. Do **not** mark false positive unless it truly is noise.

### D. Customer portal check

Customer **Alerts** — same title, plain-English summary only (no raw JSON, no internal IPs if customer-safe mode applies).

### E. Cleanup

Leave alert/incident open for demo, or set alert **closed** after walkthrough.

---

## Service 2 — Incident Response & Casework

**What this service is:** SOC cases with assignment, timeline, customer-safe narrative.

### A. Generate

Same as Service 1 — any alert with **Wazuh level ≥ 10** auto-opens an incident:

```bash
./scripts/soc_demo_fire_detection.sh s02-incident
```

### B. Find it

1. Admin **Incidents** — new `INC-ALPHAWINCORP-6VS2-TH-####`.
2. Admin **Dashboard** — **Active Incidents** = 1.

**Pass:** Incident status **open**, linked to primary alert.

### C. SOC analyst work

1. Open incident **TH-####**.
2. Assign **Demo SOC Analyst**.
3. Status → **In progress**.
4. Fill **Customer visible summary** and **Customer action required**.
5. **Add comment** (internal): investigation notes.
6. **Add comment** (customer): “SOC is investigating; please confirm with IT…”
7. Admin **Recommendations → Create** — link to this incident, customer visible.

**Do not** create dozens of CVE incidents — one good case beats fifty noise tickets.

### D. Customer portal check

**Incidents** → open case → read summary and action.  
**Recommendations** → linked item.

### E. Hero case for live demo

Existing rehearsal case (if still open): **INC-ALPHAWINCORP-6VS2-TH-0060** — use this on stage; close after demo with resolution note.

---

## Service 3 — Security Automation & Containment

**What this service is:** Active response (isolate host, kill process) — **show capability, don’t fire unplanned**.

### A. Generate

**Do not isolate mid-demo unless planned.** Instead:

1. Admin **Incidents** → open your hero incident.
2. Scroll to **EDR / Containment** panel (if shown).
3. Admin **Dashboard** — EDR metrics strip (MTTC, telemetry processed).

Historical proof already in DB (past isolate/verify actions).

### B. Find it

- Incident detail → **EDR Control Panel** / process tree (collapsed forensic section).
- Mention **verified** containment rows from lab history.

### C. SOC analyst work (talk track)

1. “We can isolate in one click — lab only today.”
2. Show **Execute** buttons greyed or explain role gate.
3. **Do not** click **Isolate** on production/demo Windows server without approval.

### D. Optional live lab (only if you explicitly approve)

On incident detail → EDR → **Isolate host** on a **named lab VM** — then **Unisolate** and show status **verified**.

### E. Pass

Audience understands containment path exists; no accidental outage.

---

## Service 4 — Vulnerability Management (VMaaS)

**What this service is:** Scan findings → SOC triage → **customer recommendations** (not SOC incidents).

### A. Generate / refresh findings

```bash
./scripts/soc_demo_fire_detection.sh s04-vmaas-sync
```

This calls live Nuclei/Vuls/Greenbone ingest on VM 109.

### B. Find it

1. Admin **Vulnerabilities** — open **HIGH** / **CRITICAL** rows for Alpha.
2. Customer **Vulnerabilities** (`:3001/vulnerabilities`) — summary counts.

**Pass:** At least one open finding; sync message `live_ingest` or completed scan.

### C. SOC analyst work

1. Admin **Vulnerabilities** → click a finding → read detail.
2. Click **Promote to recommendation**.
3. Tick **Customer visible**.
4. Save — customer gets patch guidance, not a SOC incident.

**Rule:** CVEs → VMaaS + recommendations. **Not** 46 open incidents.

### D. Customer portal check

**Vulnerabilities** + **Recommendations** — promoted item visible.

---

## Service 5 — Continuous Compliance (CaaS)

**What this service is:** Wazuh SCA benchmark scores → compliance dashboard.

### A. Generate / refresh

```bash
./scripts/soc_demo_fire_detection.sh s05-compliance-sync
```

### B. Find it

1. Customer **Compliance** (`:3001/compliance`) — score ~27%, failed checks list.
2. (Optional) API: admin sync returns passed/failed counts.

**Pass:** `has_data: true`, hundreds of checks listed.

### C. SOC analyst work

1. Pick **one failed control** (e.g. password policy, audit policy).
2. Admin **Recommendations → Create** for Alpha:
   - Title: “Remediate failed CIS control: …”
   - Priority: medium/high
   - **Customer visible:** ON
3. Explain low score on **evaluation Windows Server** is expected in lab.

### D. Customer portal check

**Compliance** page + new recommendation.

---

## Service 6 — Network Detection & Response (NDR)

**What this service is:** Network sensor alerts (Suricata/Zeek) — east-west / C2 / DNS anomalies.

### A. Generate

**Sync adapter data:**

```bash
./scripts/soc_demo_fire_detection.sh s06-ndr-sync
```

**Optional real sensor (VM 106, `192.168.0.216`):** generate harmless traffic (ping sweep is enough for lab discussion) — real Suricata rule **86601** path exists but may need tuning.

### B. Find it

1. Customer **Network Detection** (`:3001/ndr`) — events, sensors.
2. Talk track: Suricata on VM 106 is **live**; portal rows may include adapter samples until a fresh sensor event maps.

### C. SOC analyst work

1. Show event categories (C2, lateral movement, port scan).
2. **Do not** claim sample rows are from today’s PowerShell demo unless they are.
3. If a real NDR alert exists → triage like Service 1 (alert + optional incident).

### D. Honesty line

“Sensor is live; we’re showing the NDR workflow. New customer traffic populates these rows from the sensor, not from endpoint alerts.”

---

## Service 7 — Threat Intelligence & Enrichment

**What this service is:** IOCs and campaigns enrich cases.

### A. Generate / refresh

```bash
./scripts/soc_demo_fire_detection.sh s07-ti-sync
```

Or Admin UI: **Threat Intel** (`:3000/threat-intel?tenant=ALPHAWINCORP-6VS2`) → **Sync enrichment**.

### B. Find it

1. Admin **Threat Intel** — IOC list, campaigns for Alpha.
2. Customer **Threat Intel** (`:3001/threat-intel`).

**Pass:** ~6 IOCs, campaigns visible; sync source `misp_vm108`.

### C. SOC analyst work

1. Tie back to **Service 1 alert**: “We enrich endpoint detections with threat feeds.”
2. Optional: **STIX paste ingest** on Threat Intel page (lab IOC bundle).
3. No customer-facing vendor brand names — use “Global Threat Intelligence Engine” copy.

---

## Service 8 — Endpoint Forensics & Deception

**What this service is:** Deep collection / deception tripwires — customer sees **metadata only**.

### A. Generate / refresh

```bash
./scripts/soc_demo_fire_detection.sh s08-forensics-sync
```

**Optional live collect (Linux lab VM 105, `192.168.0.215`):** Velociraptor client enrolled to VM 110 — SOC triggers collect from Admin incident **EDR → Collect forensics** (metadata returns to portal).

### B. Find it

1. Customer **Forensics** (`:3001/forensics`) — tripwires, collections, events.
2. Admin incident detail → EDR collect status if you ran collect.

### C. SOC analyst work

1. Explain tripwire rows may be **sample UX** until live deception sensors ship.
2. Show collection **status** (running/ready) — customer never gets raw artifact path in portal.
3. Link forensics narrative to **Service 1** incident.

---

## Service 9 — External Attack Surface (EASM)

**What this service is:** Internet-facing asset discovery — **no agents on customer LAN**.

### A. Generate

```bash
./scripts/soc_demo_fire_detection.sh s09-easm-scan
```

Or Customer **Attack Surface** → register a domain you control → start scan.

### B. Find it

1. Customer **Attack Surface** (`:3001/easm`) — assets, findings, open ports.
2. Wait for VM 109 EASM agent cycle if async.

### C. SOC analyst work

1. Review new external findings.
2. **Promote** critical finding to **recommendation** (same pattern as VMaaS).
3. Emphasize: “We see your perimeter like an attacker — zero endpoint install.”

---

## Service 10 — Cloud & Identity Protection (ITDR)

**What this service is:** SaaS identity threats (M365/Entra) — **adapter today, live Graph when connected**.

### A. Generate / refresh

```bash
./scripts/soc_demo_fire_detection.sh s10-itdr-sync
```

### B. Find it

1. Customer **Cloud & Identity** (`:3001/itdr`) — identity events, posture score.

### C. SOC analyst work

1. Walk through sample events (MFA fatigue, risky sign-in, mail rule).
2. **Say clearly:** “Live Microsoft 365 connection is the upgrade step — today you see the workflow and adapter enrichment.”
3. Do **not** claim live Entra detection until Graph secrets are configured.

---

## Bonus — Beta appliance path (edge + tenant isolation)

**Story:** Beta customer has on-prem appliance; metadata forwards to SOC; Beta cannot see Alpha.

1. Customer **Beta** `:3001` → **Assets** → appliance **online** (heartbeat).
2. Try Alpha incident URL while logged in as Beta → **404** (not 403).
3. Beta **Services** page — only core + entitled add-ons (not full 10-card Alpha).
4. Optional: generate alert on Beta appliance LAN (future step — local Wazuh on VM 226 → telemetry ingest).

---

## CISO extras ( weave into any scenario)

| Topic | Demo action |
|-------|-------------|
| Tenancy | Beta → Alpha data = 404 |
| Entitlements | Beta nav hides unpurchased services |
| Commercial | **Services** — INCLUDED vs AVAILABLE → **Request consulting** |
| Reports | After closing a case: Admin **Reports** → generate PDF for Alpha |
| Audit | Admin **Audit** — show SOC actions logged |
| Appliance | Beta heartbeat + “metadata only leaves the edge box” |

---

## Demo-day rules

- Lab VMs only · No malware · No unplanned isolate  
- **One hero incident** open during the room demo (TH-0060 or newest)  
- Close stale noise — don’t show 56 open tickets  
- If data is adapter-seeded, **say so first**  
- Alpha = full catalog · Beta = appliance + core  

---

## Quick command reference

| Service | Fire command |
|---------|----------------|
| Log / IR (PowerShell) | `./scripts/soc_demo_fire_detection.sh s01-powershell` |
| Log (Netsh) | `./scripts/soc_demo_fire_detection.sh s01-netsh` |
| VMaaS | `./scripts/soc_demo_fire_detection.sh s04-vmaas-sync` |
| Compliance | `./scripts/soc_demo_fire_detection.sh s05-compliance-sync` |
| NDR | `./scripts/soc_demo_fire_detection.sh s06-ndr-sync` |
| Threat Intel | `./scripts/soc_demo_fire_detection.sh s07-ti-sync` |
| Forensics | `./scripts/soc_demo_fire_detection.sh s08-forensics-sync` |
| EASM | `./scripts/soc_demo_fire_detection.sh s09-easm-scan` |
| ITDR | `./scripts/soc_demo_fire_detection.sh s10-itdr-sync` |

---

## Suggested order for your rehearsal day

1. **Services 1 + 2** — fire PowerShell → full SOC loop → customer tabs  
2. **Service 4** — VMaaS sync → promote finding  
3. **Service 5** — compliance sync → one recommendation  
4. **Service 7** — threat intel sync → tie to incident  
5. **Services 6, 8, 9, 10** — sync + customer pages + honesty talk track  
6. **Service 3** — EDR history + optional isolate (if approved)  
7. **Bonus** — Beta isolation + appliance heartbeat  
8. Close hero case with resolution note + optional monthly report  

---

*Updated: step-by-step controlled test runbook with triggers, portal paths, and SOC actions per catalog service.*

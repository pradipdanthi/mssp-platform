# Incident action brief — INC-ALPHAWINCORP-6VS2-TH-0060

**Customer:** Alpha-Win-Corp (`ALPHAWINCORP-6VS2`)  
**Status:** In progress  
**Severity:** High  
**Assigned SOC analyst:** Demo SOC Analyst  
**Opened:** 12 Aug 2026, 18:22 IST  

---

## 1. What happened (plain English)

Our monitoring detected **unusual encoded PowerShell** on a Windows server named **WIN-BL72S84GDTF**. Encoded PowerShell is often used to hide malicious commands. It can also appear during legitimate admin work — that is why SOC opened a case and asked IT to confirm.

**There is no confirmed data theft at this time.** This is a controlled lab/demo detection for rehearsal.

---

## 2. What SOC has already done

- [x] Alert ingested into the control plane (Wazuh → MSSP portal)
- [x] High-severity case auto-opened: **INC-ALPHAWINCORP-6VS2-TH-0060**
- [x] Assigned to **Demo SOC Analyst**
- [x] Customer-visible summary published on the alert
- [x] Customer comment added on the incident
- [x] Customer recommendation created (high priority, visible)

---

## 3. Actions for you to perform now

### A. As SOC (Admin portal — port 3000)

1. Open the incident:  
   `http://192.168.0.201:3000/incidents/1dcd3c34-92ca-44f7-ba3c-871bdc46c183`
2. Read **Customer summary** and **Customer action required** — confirm wording is clear for a non-technical customer.
3. Open the linked alert:  
   `http://192.168.0.201:3000/alerts/e5231166-22dc-4003-8941-479144655cc8`
4. Confirm **Customer visible** is ON and the plain-English summary is present.
5. Add one **internal** comment (example):  
   *“Waiting on customer IT confirmation whether encoded PowerShell was an approved admin change.”*
6. **Do not** run EDR isolate/kill on this host unless you explicitly plan that as a separate demo step.

### B. As customer IT (Customer portal — port 3001)

Log in as `admin@alphawin.com` (lab password from your validation setup).

1. **Dashboard** — confirm open incidents shows **1**.
2. **Alerts** — find *“SOC demo: suspicious encoded PowerShell on Windows workstation”*.
3. **Incidents** — open **INC-ALPHAWINCORP-6VS2-TH-0060** and read the SOC summary.
4. **Recommendations** — open *“Confirm unexpected PowerShell activity on Windows server”*.

**Customer IT checklist (what you would tell the room):**

- [ ] Confirm with the server admin whether anyone ran encoded PowerShell around the incident time.
- [ ] If **yes, approved change** → note the change ticket / admin name and reply to SOC.
- [ ] If **no, not approved** → disable that admin session, do not reboot yet, call SOC.
- [ ] Do **not** delete logs or re-image until SOC confirms.

### C. Close the loop (after you walk the demo)

When you are finished showcasing the case:

1. Admin → Incidents → set status to **Resolved** or **Closed**.
2. Add resolution note (example):  
   *“Customer IT confirmed this was an approved lab/demo PowerShell test. No malicious activity. Case closed.”*
3. Optionally mark the related recommendation **completed**.

---

## 4. Customer-visible text (copy you should see in the portal)

### SOC summary

> Our SOC is investigating unusual PowerShell activity on a Windows server in your environment. There is no confirmed data theft at this time. We will update this case as we complete checks.

### Customer action required

> Please confirm with your IT admin whether anyone ran an encoded PowerShell command on this Windows server around this time. If this was not an approved change, disable that admin session and call SOC.

### Alert summary (customer-safe)

> We detected unusual PowerShell activity on one of your Windows servers. This can be a sign of an attacker trying to run hidden commands. Our SOC is investigating and has opened a case.

### Recommendation

> SOC detected encoded PowerShell on a Windows server. IT should confirm whether this was an approved administrative change. If not, disable the session and contact SOC before restoring access.

---

## 5. Demo talking points (30-second version)

1. **Detect** — “We saw encoded PowerShell in seconds, not next week.”
2. **Case** — “A real incident was opened automatically because severity was high.”
3. **Human SOC** — “An analyst was assigned; we wrote plain English for the customer.”
4. **Customer control** — “They only see what we approve — no raw logs, no vendor console.”
5. **Action** — “Here is exactly what IT must do while we investigate.”

---

## 6. Reference IDs (for support / admin only)

| Item | Value |
|------|--------|
| Incident number | INC-ALPHAWINCORP-6VS2-TH-0060 |
| Incident UUID | `1dcd3c34-92ca-44f7-ba3c-871bdc46c183` |
| Alert UUID | `e5231166-22dc-4003-8941-479144655cc8` |
| Recommendation UUID | `8456c7d0-0570-4e52-b563-69e05a25d1ba` |
| Affected asset | WIN-BL72S84GDTF (Windows Server 2022 Evaluation) |
| MITRE | T1059.001 PowerShell / Execution |

---

*Generated from live control-plane data on VM 100. This is a lab rehearsal case — safe to close after your walkthrough.*

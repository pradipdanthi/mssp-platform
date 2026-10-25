# KB-113 — ITDR Entra one-click containment (revoke / reset / disable)

**Status:** Implemented in control plane (2026-10-25); **live M365 trial validation deferred** (owner will return).  
**Related:** Silver Cloud & Identity ITDR; `itdr_graph_client.py`, `itdr_service.py`, customer `/itdr` portal.

---

## 1. Purpose

Give **designated customer admins** and **SOC admins** a single NikTiar action that executes Microsoft Entra containment via Graph:

1. **Revoke sessions** — `POST /users/{id}/revokeSignInSessions`  
2. **Temporary password + force change at next sign-in** — `passwordProfile`  
3. **Disable account** — `accountEnabled: false`

NikTiar does **not** sit in the Microsoft login/MFA prompt. MFA remains Entra. NikTiar **monitors** (read) and optionally **contains** (write) with consented app permissions.

---

## 2. Delivery readiness (honest)

| Capability | Ready? |
|---|---|
| Connect M365 domain in customer portal | Yes |
| Graph **read** sync (sign-ins / directory audits) | Yes (needs `AZURE_*` secrets) |
| ITDR events + playbook text in customer UI | Yes |
| One-click contain API + customer button | **Yes (code)** |
| Admin SOC remediate API | **Yes (code)** |
| Admin dedicated ITDR page UI | Partial (API client helper only) |
| Lab/prod Graph secrets on this host | **Not configured** until trial |
| End-to-end demo on trial M365 | **Pending owner test** |

Default commercial model remains: **detect + guide** without write consent. One-click is for tenants that **explicitly** consent Graph write permissions.

---

## 3. APIs

### Customer (role: `customer_admin`)

`POST /customer/itdr/{short_code}/remediate`

```json
{
  "user_principal_name": "alice@contoso.com",
  "event_id": "<optional uuid>",
  "revoke_sessions": true,
  "reset_password": true,
  "disable_account": true,
  "confirm": true
}
```

`confirm` must be `true` or the API returns 422.

### Admin / SOC (`ADMIN_SOC_ROLES`)

`POST /admin/itdr/{tenant_ref}/remediate` — same body (`tenant_ref` = UUID or short_code).

### Response (password once)

Returns `temporary_password` to the actor only. **Not** persisted in DB. Audit stores steps + UPN, not the password.

---

## 4. UI

- **Customer portal** → Cloud & Identity (`ItdrPage`): expand event → **Contain identity (revoke · reset · disable)** (admins only).  
- Shows temp password panel once after success.  
- **Admin:** `remediateAdminItdrIdentity()` in `frontend-admin/src/api/admin.ts` (wire full page later).

---

## 5. Trial M365 setup (when owner returns)

1. Entra **App registration** in the trial tenant.  
2. Admin consent **application** permissions:
   - Read: `AuditLog.Read.All`, `User.Read.All` (and/or `Directory.Read.All`)  
   - Write: `User.ReadWrite.All`, `User.RevokeSessions.All` (and/or `User.EnableDisableAccount.All`)  
3. Client secret → control plane:
   - `AZURE_TENANT_ID`  
   - `AZURE_CLIENT_ID`  
   - `AZURE_CLIENT_SECRET`  
   (env or `/run/secrets` / `.secrets` file mounts already supported by `itdr_graph_client`)  
4. Customer portal: Connect Microsoft 365 domain; sync.  
5. Test on a **disposable** user; verify in Entra: sessions revoked, disabled, force-change password profile.  
6. Re-enable user; sign in with temp password; confirm forced password change.

---

## 6. Security / product rules

- Only `customer_admin` (tenant-scoped) or SOC admin roles.  
- `confirm=true` required.  
- Audit: `itdr.remediate_identity` SUCCESS/FAILED.  
- Do not require standing Global Admin interactive login; use **consented app**.  
- Customers who refuse write consent: hide/disable button (future entitlement flag recommended: `itdr_graph_write_enabled`).  
- Multi-tenant MSSP later: prefer **per-tenant** Graph credentials or multi-tenant app + admin consent — today platform uses one `AZURE_*` set (fine for single trial / lab).

---

## 7. Code map

| Path | Role |
|---|---|
| `backend-api/app/services/itdr_graph_client.py` | Graph read + write helpers |
| `backend-api/app/services/itdr_service.py` | `remediate_identity_account()` |
| `backend-api/app/api/routes/itdr.py` | Customer + admin remediate routes |
| `frontend-customer/src/pages/ItdrPage.tsx` | Contain button + result panel |
| `frontend-customer/src/api/customer.ts` | `remediateItdrIdentity` |
| `frontend-admin/src/api/admin.ts` | `remediateAdminItdrIdentity` |

---

## 8. Related pending product notes

- **Secure Edge** (Cloudflare-alternative appliance) — architecture agreed; **not started** (separate from Edge Node).  
- **rclone Google OAuth own client** — held until owner decides.  
- Zeek MSSP rule IDs renumbered to **110100–110112** (platform verify PASS).

---

## 9. Resume checklist (owner)

- [ ] Create trial Entra app + consent write permissions  
- [ ] Install `AZURE_*` on `mssp-backend-api` and restart  
- [ ] Live contain test on disposable UPN  
- [ ] Optional: Admin ITDR page UI  
- [ ] Optional: entitlement flag for write remediation  

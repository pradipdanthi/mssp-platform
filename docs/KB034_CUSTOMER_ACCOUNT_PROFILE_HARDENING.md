# KB-034 — Customer Account / Profile Hardening

Status: Validated (pending tag).  
Branch: `kb034-customer-account-profile-hardening`

## Purpose

Harden the customer Account page so a logged-in customer can:

1. See phone on their profile (plus existing identity/tenant fields)
2. Update **full_name** and **phone** only
3. Change their own password (current + new)

Email, role, tenant, and status remain SOC/admin-managed. No forgot-password flow in this KB.

## Endpoints

### Existing (enhanced)

```http
GET /auth/me
```

`UserPublic` now includes optional `phone`. Still never includes password/hash.

### New

```http
PATCH /auth/me
Authorization: Bearer <access_token>
Content-Type: application/json

{ "full_name": "...", "phone": "..." }
```

- `extra=forbid` — cannot send email/role/tenant/status/password
- At least one of `full_name` / `phone` required
- Returns updated `UserPublic`

```http
POST /auth/change-password
Authorization: Bearer <access_token>
Content-Type: application/json

{ "current_password": "...", "new_password": "..." }
```

- New password minimum length: 8
- Wrong current password → 401
- Response: `{ "status": "ok", "message": "Password updated" }` — never returns password material
- `current_password` / `new_password` are treated as sensitive in 422 error redaction

## Frontend

- `AccountPage.tsx`: read-only identity/tenant panel + Profile form + Change password form
- `api/auth.ts`: `updateMyProfile`, `changePassword`; `UserPublic.phone`
- `AuthContext`: `setUser` / `refreshUser` helpers
- No `/admin` usage

## Validation command

```bash
cd /opt/mssp-control
chmod +x scripts/kb034_validate_customer_account_profile_hardening.sh
./scripts/kb034_validate_customer_account_profile_hardening.sh
```

The script will **prompt for** the `customer.viewer@demo.local` password.  
It temporarily changes the password during the test and restores it before finishing.

Expected final line:

```text
KB-034 CUSTOMER ACCOUNT PROFILE HARDENING VALIDATION PASSED
```

## Manual browser checklist

1. Open `http://localhost:3001` and sign in as `customer.viewer@demo.local`
2. Open **Account**
3. Confirm email/role/tenant are shown but not editable
4. Update name/phone and save
5. Change password (optional manual check) — remember the new password if you do

## Deferred

- Forgot-password / email reset
- MFA / 2FA
- Email change by customer
- Session device list / forced logout-all
- Admin UI changes for the same flows

# KB-033 — Customer Notifications API and Notifications Page

Status: Implemented (pending validation/commit).  
Branch: `kb033-customer-notifications-history`

## Purpose

Give each customer a dedicated, read-only **Notifications** page showing notification history for their own tenant. List-only in this KB — no detail page, no acknowledge/write workflow, no Dashboard widget.

## Table used

`notification_events` in `postgres/init/001_mssp_core_schema.sql`.

## Endpoint

```http
GET /customer/notifications/{short_code}
Authorization: Bearer <access_token>
```

Auth: `get_current_user` → resolve tenant by `short_code` → `require_tenant_match` (404 on mismatch) → parameterized:

```sql
WHERE tenant_id = %s
ORDER BY created_at DESC
LIMIT 100
```

## Response shape

```json
{
  "tenant": { "id": "...", "name": "...", "short_code": "DEMO" },
  "notifications": [
    {
      "notification_id": "<uuid>",
      "notification_type": "email",
      "status": "sent",
      "message_body": "...",
      "sent_at": "...",
      "delivered_at": "...",
      "created_at": "..."
    }
  ]
}
```

## Safe fields

`notification_id`, `notification_type`, `status`, `message_body`, `sent_at`, `delivered_at`, `created_at`.

## Hidden / forbidden fields

`tenant_id`, `incident_id`, `alert_id`, `recipient_name`, `recipient_address`, `provider`, `provider_message_id`, `error_message`, `acknowledged_at`, secrets/tokens/hashes, IPs, raw JSON, stack traces, backend internals.

## Tenant isolation

DEMO customer cannot call `/customer/notifications/DEMO2` (404). SQL always filters by resolved `tenant_id`.

## Frontend behavior

- `getCustomerNotifications(shortCode)` → `/api/customer/notifications/{shortCode}`
- Route `/notifications` (`NotificationsPage.tsx`)
- Sidebar nav item **Notifications**
- Loading / error / empty / read-only table
- No `/admin` under `frontend-customer/src`
- Dashboard unchanged in KB-033

## Validation command

```bash
cd /opt/mssp-control
chmod +x scripts/kb033_validate_customer_notifications_api_ui.sh
./scripts/kb033_validate_customer_notifications_api_ui.sh
```

Or: `CUSTOMER_VIEWER_PASSWORD='...' ./scripts/kb033_validate_customer_notifications_api_ui.sh`

Expected final line: `KB-033 CUSTOMER NOTIFICATIONS API UI VALIDATION PASSED`

## Manual browser checklist

1. Open `http://localhost:3001`, sign in as `customer.viewer@demo.local`.
2. Open **Notifications** in the sidebar.
3. Confirm read-only list of type/status/message/timestamps.
4. Network: only `/api/customer/notifications/...` — never `/admin/*`.

## Deferred

- Notification detail page
- Acknowledge / mark-read workflow
- Dashboard notifications widget
- Related incident/alert drill-down
- Showing recipient address/name
- Admin notification composer UI

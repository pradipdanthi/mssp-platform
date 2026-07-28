# KB-076 — Customer Service Upgrade Requests (Vulnerability Management)

Status: **Implemented** on control plane (VM 100).

## Goal

Vulnerability Management is an **optional** subscribed service. When a customer does not have it
enabled, the customer portal **Vulnerabilities** page shows a locked state. Clicking
**Upgrade Subscription** opens a form where they describe what they need. The request is stored
for the MSSP team (Admin → Vulnerabilities → Customer upgrade requests).

## Customer form fields

- Preferred scan cadence
- Scan scope (external, internal, authenticated, cloud, web apps)
- Approximate asset count
- Environments
- Urgency
- Compliance drivers (optional)
- Free-text “what are you looking for?”
- Preferred contact + phone

## APIs

- `POST /customer/service-upgrade-requests/{short_code}`
- `GET /customer/service-upgrade-requests/{short_code}`
- `GET /admin/service-upgrade-requests`

Tenant isolation: wrong tenant → **404**.

## Apply + validate

```bash
cd /opt/mssp-control
chmod +x scripts/kb076_create_service_upgrade_requests.sh scripts/kb076_validate_service_upgrade_requests.sh
./scripts/kb076_create_service_upgrade_requests.sh
./scripts/kb076_validate_service_upgrade_requests.sh
docker compose up -d --build backend-api frontend-customer frontend-admin
```

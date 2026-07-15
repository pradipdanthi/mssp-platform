# KB-018 — Admin Frontend Foundation Completion

## Status

Validated and ready for commit.

## Purpose

KB-018 adds the first browser-based admin frontend for the Kestrel Cyber Control Plane.

## Branding

Final branding:

- Legal entity: Cicilia Consultancy
- Operating brand: Keroxsys
- Product/platform brand: Kestrel Cyber
- Portal name: Kestrel Cyber Control Plane
- Support email: soc@keroxsys.com
- Future portal domain: portal.keroxsys.com

Runtime branding config:

frontend-admin/public/app-config.json

Logo assets:

frontend-admin/public/brand/kestrel-mark.svg
frontend-admin/public/brand/kestrel-logo.svg

The SVG logo files contain artwork only. Product/company/legal text comes from runtime config.

## Frontend stack

- React
- TypeScript
- Vite
- Docker Compose
- Runtime app config
- Vite proxy from /api to backend-api:8000

## Docker Compose

KB-018 adds the frontend-admin service.

Access URLs:

- VM: http://localhost:3000
- Laptop: http://192.168.0.201:3000

## Dependency strategy

frontend-admin/package-lock.json is included.

frontend-admin/Dockerfile uses npm ci for reproducible installs.

## Backend safety

KB-018 does not modify:

- backend-api/
- postgres/init/
- .env
- database schema
- database migrations
- backend RBAC
- backend tenant isolation
- KB-017 appliance credential API behavior

## Validation result

Final validation passed:

KB-018 ADMIN FRONTEND FOUNDATION VALIDATION PASSED

Validation confirmed:

- frontend-admin files exist
- docker-compose.yml defines frontend-admin service
- backend-api has no diff
- postgres/init has no diff
- .env was not modified
- frontend image builds
- frontend container starts
- backend-api is running
- postgres is healthy
- redis is healthy
- frontend-admin is running
- /api/health proxy reaches backend-api
- app-config.json contains Kestrel Cyber / Keroxsys / Cicilia Consultancy values
- brand SVG assets are served
- old visible MSSP Control Plane branding is removed
- required frontend routes exist
- TypeScript/Vite production build passes
- no obvious frontend secret literals were found
- KB-017 credential endpoints still exist in backend OpenAPI
- package-lock.json exists
- Dockerfile uses npm ci

## Manual browser validation

Manual browser validation was done at:

http://192.168.0.201:3000

Observed:

- Login page loaded
- Login succeeded
- Kestrel Cyber branding appeared
- Sidebar appeared
- Incidents page rendered
- Runtime portal layout worked in browser

## Demo data note

Demo SOC Manager and demo tenant/incident names come from demo database records, not product branding.

Demo data separation should be handled in a future production bootstrap module.

## Follow-ups

Recommended future modules:

- Activation Token Management UI
- Production Bootstrap and Demo Data Separation
- Customer Dashboard Foundation
- Frontend Dependency Audit and Production Build Hardening
- Reverse Proxy / HTTPS / Production Compose Profile
- Cloud Deployment Preparation

## Final state

KB-018 establishes the first working branded admin console for Kestrel Cyber Control Plane by Keroxsys, operated under Cicilia Consultancy, without changing backend logic or database schema.

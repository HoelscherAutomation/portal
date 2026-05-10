# Hoelscher Employee Portal

Self-hosted modular employee portal. See `docs/superpowers/specs/2026-05-09-employee-portal-design.md` for the full product design.

## Quick start (local dev)

```bash
cp .env.example .env
docker compose up -d

# Apply migrations
docker compose exec backend alembic upgrade head

# Create initial admin user (interactive)
docker compose exec backend python -m scripts.create_admin

# Run tests
docker compose exec backend pytest
```

Then open <http://localhost:5173>.

## Default ports

| Service  | Port  |
|----------|-------|
| Frontend | 5173  |
| Backend  | 8000  |
| Postgres | 5432  |
| Redis    | 6379  |

All configurable via `.env`.

## Architecture

- `backend/` — FastAPI + async SQLAlchemy + fastapi-users
- `frontend/` — SvelteKit + Tailwind v4
- `docker-compose.yml` — postgres + redis + backend + frontend

## What works (P0a + P0b + P0c + P0d.2b)

### Foundation (P0a)
- `docker compose up` brings up all services
- Login at `/login`, blank authenticated home, admin route skeleton (superuser only)
- `GET /api/health`, `GET /api/me`, `POST /api/auth/login`, `POST /api/auth/logout`
- Cookie-based session auth (HttpOnly, JWT-strategy)

### Tenant branding (P0b)
- `tenant_config` table with single seeded row (id=1)
- `GET /api/tenant/config` (any authenticated user)
- `PUT /api/tenant/config` (superuser-only, updates name/color/welcome message)
- `POST /api/tenant/logo` (superuser-only, multipart upload, validates image)
- `/uploads/<filename>` serves uploaded logos
- Admin Branding form at `/admin/branding` lets superusers edit branding live
- Header + page title use tenant config

### Module catalog (P0c)
- Code-defined module registry with 7 modules (`app/modules/registry.py`)
- `GET /api/modules` returns combined registry + enablement + request state
- `POST /api/modules/{key}/request` creates a customer request (409 on duplicate)
- Admin Modules catalog at `/admin/modules` shows all 7 module cards
- Customer admin can click "Request" → "Requested" badge appears
- Requests accumulate in `module_requests` table for Operator Console (P0d) to fulfill

### Phone-home client (P0d.2b)
- Background asyncio loop runs every `PHONE_HOME_INTERVAL_SECONDS` (default 300)
- Builds heartbeat payload (version + enabled modules + pending requests + uptime) from local DB
- POSTs to `OC_URL/api/phone-home` with `Bearer OC_TOKEN`
- Applies returned actions: `enable_module`, `disable_module`, `mark_request_fulfilled`
- Acks each action back to OC with ok/error
- Opt-in: if `OC_URL` is unset, the loop never starts (portal runs standalone)

## What's next

P0d.3 deploys the OC to Outpost (Caddy + Cloudflare DNS + TLS at `oc.hoelscherautomation.com`).
P1 adds the Ask Docs RAG module — the first live module that actually does real work.

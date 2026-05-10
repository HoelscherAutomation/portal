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

## What works (P0a + P0b)

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

## What's next

Subsequent plans add the module registry and admin module catalog (P0c), the
Operator Console (P0d), production deployment (P0e), and the Ask Docs RAG
module (P1).

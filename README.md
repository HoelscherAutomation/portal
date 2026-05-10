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

## What works in P0a (this plan)

- `docker compose up` brings up all services
- Login at `/login`, blank authenticated home page, admin route skeleton (superuser only)
- `GET /api/health`, `GET /api/me`, `POST /api/auth/login`, `POST /api/auth/logout`
- Cookie-based session auth (HttpOnly, JWT-strategy)

## What's next

Subsequent plans add tenant config + theming (P0b), the module registry and admin module catalog (P0c), the Operator Console (P0d), production deployment (P0e), and the Ask Docs RAG module (P1).

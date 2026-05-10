# Hoelscher Employee Portal

Self-hosted modular employee portal. See `docs/superpowers/specs/2026-05-09-employee-portal-design.md` for the full product design.

## Quick start (local dev)

```bash
cp .env.example .env
docker compose up -d
docker compose exec backend python -m scripts.create_admin
```

Then open <http://localhost:5173>.

## Architecture

- `backend/` — FastAPI + async SQLAlchemy + fastapi-users
- `frontend/` — SvelteKit + Tailwind v4
- `docker-compose.yml` — postgres + redis + backend + frontend

## Tests

```bash
docker compose exec backend pytest
docker compose exec frontend npm test
```

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

## What works (P0a + P0b + P0c + P0d.2b + P1.1 + P1.2)

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

### Ask Docs ingestion (P1.1)
- New services in compose: `qdrant` (vector store), `ollama` (embeddings), `worker` (arq)
- `ask-docs` module is now LIVE in the registry (was preview)
- Upload PDF/DOCX/TXT/MD via `/modules/ask-docs/library` (also via `POST /api/modules/ask-docs/documents`)
- Background worker parses → chunks (1024 tok / 128 overlap) → embeds via local Ollama → stores in Qdrant
- Library page shows status: pending → indexing → indexed (or failed with error)
- Delete removes both the file on disk and its vectors from Qdrant
- First-boot pulls `nomic-embed-text` (~300MB) into Ollama; ~30-60s on first install

### Ask Docs chat (P1.2)
- `POST /api/modules/ask-docs/chat` streams an answer via SSE; events: `sources`, `delta`, `final`, `error`
- Default LLM: Anthropic via `ANTHROPIC_API_KEY` env var (returns 503 cleanly if unset)
- Retrieval: top-K (default 8) chunks from Qdrant via cosine on the question's embedding
- LLM gets a system prompt forcing `[N]` citations + a "no info" fallback
- Citation parser dedupes + filters out hallucinated source numbers (any `[N]` where `N > len(sources)`)
- Hallucination guard replaces zero-citation substantive answers with the canonical "no info" message
- Mid-stream LLM failures emit a final `error` SSE event so the frontend can show a clean failure (HTTP headers were already sent — can't return 5xx)
- Each query persisted to `ask_docs_queries` (for the P1.4 admin dashboard) — DB-persist failures log but don't abort the stream
- `GET /api/modules/ask-docs/chunks/{doc_id}/{chunk_index}` for source-preview drill-down (used by P1.4 query log)
- Frontend `/modules/ask-docs` is now the actual chat: input box + answer area with clickable `[N]` pills + side pane source preview (text-based: filename + page + chunk content)
- Source preview is text-only in v1; PDF page rendering is a P1.x candidate

## What's next

P1.3 adds LLM mode config UI (Anthropic / Ollama / Hoelscher proxy) + Voyage upgrade option + reranker.
P1.4 adds the module admin dashboard (doc count, query log, usage stats).
P1.5 adds watched folder + backup/restore.

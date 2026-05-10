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

## What works (P0a + P0b + P0c + P0d.2b + P1.1 + P1.2 + P1.3 + P1.4)

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

### Ask Docs LLM mode config (P1.3 MVP)
- New admin page `/admin/modules/ask-docs/config` — superuser-only, linked from the `/admin/modules` catalog when ask-docs is enabled
- Switch chat backend between Anthropic and BYO Ollama via radio (Hoelscher proxy stubbed as "Coming soon")
- API keys encrypted at rest in new `module_configs` table via Fernet (key derived from `SECRET_KEY` via HKDF, domain-separated by HKDF salt/info)
- Per-mode "Test" probe button runs a 1-token round-trip with 10s timeout — verifies config before saving; never persists the test value
- Probe handles `{_set: true}` markers so customers can re-test the saved key without re-entering it
- Generic `module_configs` table reusable across future modules; per-module Pydantic schemas + `SECRET_PATHS` registry validate writes
- `GET / PUT / POST probe` under `/api/admin/modules/{module_key}/config` — superuser only; secrets always redacted in API responses
- New `make_llm_client()` dispatcher (`app/modules/ask_docs/llm_factory.py`) is now the only switch point; chat orchestrator stays mode-agnostic
- New `OllamaChatClient` matches the `ChatClient` Protocol; same `stream_chat()` interface as `AnthropicChatClient`
- `ask_docs_queries.llm_mode` now reflects the actual mode used per-query (was hardcoded "anthropic" in P1.2)
- Backwards compat: `ANTHROPIC_API_KEY` env var still works as fallback when no DB config exists — current dev setup unchanged
- Probe error responses scrub common API key patterns (`sk-...`, `Bearer ...`) before surfacing to the browser
- Voyage embeddings opt-in + nomic-rerank toggle deferred to P1.3b
- Hoelscher proxy backend deferred — UI shows "Coming soon" placeholder

### Ask Docs admin dashboard (P1.4)
- New admin page `/admin/modules/ask-docs` — superuser-only, polls every 30s
- Stats: documents (total + indexed/indexing/pending/failed breakdown), queries (30d count + avg/p95 latency), tokens (30d), estimated cost (30d) with "prices as of" tooltip
- Inline SVG bar chart shows daily token usage over the last 30 days (no chart-lib dep)
- Mode breakdown card (queries + tokens per LLM mode), Document status card
- Query log table (last 100): timestamp, user email, query, citation count, tokens, latency, mode
- Click any query row → side panel with full question, full answer, and the cited source chunks (filename + page + content) — sources persisted on the query row at chat time, no Qdrant lookup at click time
- New backend endpoints under `/api/admin/modules/ask-docs/`: `GET /dashboard`, `GET /queries?limit&offset`, `GET /queries/{id}` — all superuser-only
- New `pricing.py` module with hardcoded prices keyed by (mode, model) + `LAST_UPDATED` constant; `estimate_cost_usd()` falls back to mode-wildcard then 0
- Schema: `ask_docs_queries.sources_used` JSONB column added (default `[]`); chat orchestrator now persists the same source payload it streams in the SSE 'sources' event
- "Dashboard →" link added to the ask-docs card in `/admin/modules` alongside the existing "Configure →"

## What's next

P1.3b adds Voyage embeddings opt-in (with re-index workflow) + nomic-rerank toggle.
P1.5 adds watched folder + backup/restore.

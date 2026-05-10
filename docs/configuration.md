# Configuration Reference

Every environment variable the portal reads, what it does, when to change it.

All settings live in `.env` at the repo root (the file is gitignored — it's per-install). Compose passes them through to the backend + worker containers.

The portal validates required values at startup and refuses to boot with a missing `SECRET_KEY`, weak placeholder, or unsafe `CORS_ORIGINS`.

---

## Required (no defaults — startup fails without these)

### `SECRET_KEY`

Signs session cookies AND derives the Fernet encryption key for stored API keys (`module_configs.config` JSONB column).

- **Format:** any string ≥ 32 characters, not a known placeholder
- **Generate:** `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`
- **Rotation:** documented as a separate workflow — see [Rotating SECRET_KEY](#rotating-secret_key) below

### `POSTGRES_PASSWORD`

Postgres database password. Used by the backend to connect AND by `pg_dump` / `pg_restore` during backup/restore.

- **Format:** any string (URL-safe characters preferred to avoid escaping in `DATABASE_URL`)
- **Generate:** `python3 -c "import secrets; print(secrets.token_urlsafe(24))"`

---

## Required for chat (default LLM mode)

### `ANTHROPIC_API_KEY`

Used by the Ask Docs chat module when in "Anthropic" LLM mode (the default). Falls back gracefully if you store the key in `module_configs` via the admin UI instead — but having it in `.env` is the simplest setup for first install.

- **Format:** Anthropic API key, starts with `sk-ant-api03-...`
- **Source:** Create at https://console.anthropic.com/settings/keys (requires billing enabled)
- **Cost:** With the default `claude-sonnet-4-6` model, ~$0.005 per chat query. A 10-employee company asking 100 queries/week comes out to ~$2.20/month.
- **Skip if:** You're using Ollama (local LLM) instead — leave empty here, configure under "Configure → Ollama" in the admin UI

### `ANTHROPIC_MODEL`

- **Default:** `claude-sonnet-4-6`
- **Other options:** `claude-opus-4-7` (slower, ~5× more expensive, marginal accuracy gain for most use cases)
- **Override per install:** set in `.env`, OR per-mode via `/admin/modules/ask-docs/config`

---

## Network / TLS

### `BACKEND_PORT`

- **Default:** `8000`
- **Change if:** another service on the host already uses 8000

### `COOKIE_SECURE`

- **Default:** `false` (HTTP-friendly for local dev)
- **Set to `true`** when you put HTTPS in front (e.g., Caddy + Let's Encrypt). Without this the browser won't send the session cookie over HTTPS.

### `CORS_ORIGINS`

- **Default:** `["http://localhost:5173"]`
- **Production value:** `["https://portal.your-company.com"]` — the exact origin browsers see
- **NEVER set to `["*"]`** — startup refuses; cookies + wildcard CORS is browser-bypassable
- **Multiple origins:** JSON array — `["https://portal.your-company.com", "https://portal-staging.your-company.com"]`

---

## Operator Console (phone-home) — opt-in

If you've signed up for managed operator-console support (Hoelscher Automation pushes module enablements + update notifications to your portal), set both of these. Leave both empty to run standalone.

### `OC_URL`

- **Default:** unset
- **Production:** `https://oc.hoelscherautomation.com`
- **Effect:** when set, a background loop sends a heartbeat every 5 minutes with portal version + enabled modules + pending requests. Receives action queue back (enable/disable modules, mark requests fulfilled).

### `OC_TOKEN`

- **Default:** unset
- **Format:** opaque token issued by Hoelscher Automation when you sign up
- **Required if** `OC_URL` is set

### `PHONE_HOME_INTERVAL_SECONDS`

- **Default:** `300` (5 minutes)
- **Lower bound:** 60 (any lower starts to look like polling abuse)
- **Higher values:** fine if you don't need fast turnaround on operator actions

### `PORTAL_VERSION`

- **Default:** `0.5.0`
- **Set to:** the version of the portal you're running. Surfaced in phone-home heartbeats + backup manifests + the "What works" README header. Advance when you `git pull` a new release.

---

## Ask Docs module

These tune the RAG pipeline. Defaults are reasonable for most installs.

### `QDRANT_URL`

- **Default:** `http://qdrant:6333` (the in-compose Qdrant service)
- **Change if:** you're running Qdrant on different infrastructure (e.g., shared across multiple portal installs — uncommon, single-tenant by default)

### `OLLAMA_URL`

- **Default:** `http://ollama:11434`
- **Change if:** you have a beefier Ollama running on a different host (e.g., a GPU box) — point both embeddings AND the optional chat-mode Ollama at the same instance

### `ASK_DOCS_EMBEDDING_MODEL`

- **Default:** `nomic-embed-text` (768-dim, ~300 MB)
- **Other models:** would require recreating the Qdrant collection with the new vector size — not a runtime swap. Voyage embeddings opt-in is on the roadmap (P1.x).

### `ASK_DOCS_CHUNK_SIZE_TOKENS`

- **Default:** `1024` tokens per chunk
- **Tradeoff:** smaller chunks = more granular citations but fragmented context; larger chunks = better context but worse citation precision
- **Re-index required** if you change this — existing documents stay chunked at the old size

### `ASK_DOCS_CHUNK_OVERLAP_TOKENS`

- **Default:** `128` (12.5% overlap)
- **Effect:** prevents queries that span chunk boundaries from missing context
- **Re-index required** if changed

### `ASK_DOCS_TOP_K`

- **Default:** `8` chunks per query passed to the LLM
- **Lower:** faster, less context, possibly missing answers
- **Higher:** slower, more LLM cost, sometimes diluted answers
- **With reranker enabled:** retrieve top-24 → rerank → keep top-8 (this constant)

### `ASK_DOCS_MAX_ANSWER_TOKENS`

- **Default:** `1024`
- **Effect:** caps the LLM's response length — prevents runaway costs on a malformed prompt

---

## Internal — usually leave alone

### `DATABASE_URL`

- **Default:** auto-derived from `POSTGRES_USER` + `POSTGRES_PASSWORD` + `POSTGRES_DB` in compose
- **Format:** `postgresql+asyncpg://user:pass@host:port/dbname`
- **Override only if** Postgres is external (rare for single-tenant)

### `REDIS_URL`

- **Default:** `redis://redis:6379/0` (the in-compose Redis)
- **Override only if** you're sharing a Redis with other services

### `UPLOADS_PATH`

- **Default:** `/app/data/uploads` inside the backend + worker containers (backed by the `portal_uploads` named Docker volume)
- **Don't change** unless you understand the volume mount semantics — see `docker-compose.yml`

### `SQL_ECHO`

- **Default:** `false`
- **Set to `true`** to log every SQL statement (useful for debugging migrations or perf issues; very noisy in normal operation)

### `RESET_PASSWORD_SECRET` / `VERIFICATION_SECRET`

- **Default:** unset (falls back to `SECRET_KEY`)
- **Set separately if** you want password-reset and email-verification tokens signed with a different key from session cookies. Most installs don't bother.

---

## Rotating `SECRET_KEY`

You should rotate `SECRET_KEY` if you suspect it's been compromised (e.g., a backup file leaked, an old contributor had access, etc.). Here's the safe procedure:

1. **Decide on the rotation window.** Encrypted module-config secrets become unreadable with the old key — you'll need to re-enter them. Pick a low-traffic time.

2. **Capture the current state of secrets** that are stored in `module_configs`:
   - The Ask Docs Anthropic API key (if you saved it via the admin UI vs the env var)
   - Voyage / Hoelscher proxy keys (when those modes ship)

3. **Stop the backend + worker** (frontend can stay up):
   ```bash
   docker compose stop backend worker
   ```

4. **Generate the new key** and update `.env`:
   ```bash
   NEW_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))")
   sed -i "s|^SECRET_KEY=.*|SECRET_KEY=${NEW_KEY}|" .env
   ```

5. **Drop the now-unreadable encrypted rows:**
   ```bash
   docker compose exec -T postgres psql -U portal -d portal -c \
     "DELETE FROM module_configs;"
   ```

6. **Restart:**
   ```bash
   docker compose up -d --force-recreate backend worker
   ```

7. **Re-enter secrets via the admin UI** — visit `/admin/modules/ask-docs/config` and PUT your Anthropic API key. The new secret gets encrypted with the new SECRET_KEY.

8. **Verify chat works** by asking a question against an indexed document.

If you skip steps 5–7, the backend will throw `DecryptionError` when the chat orchestrator tries to load the API key. Easy to recover from but ugly the first time.

---

## See also

- [install.md](./install.md) — first-time setup
- [security.md](./security.md) — what these settings protect against
- [backup-restore.md](./backup-restore.md) — backups include `.env` (it's a credential)

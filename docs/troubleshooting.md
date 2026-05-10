# Troubleshooting

When something goes wrong. Symptoms first, root causes + fixes second.

If your problem isn't here, the **always-useful first step** is:

```bash
docker compose ps                              # what's running, what's healthy
docker compose logs --tail=100 backend         # most issues live here
docker compose logs --tail=50 worker           # for indexing failures
docker compose logs --tail=50 frontend         # for blank-page issues
```

---

## First-boot failures

### Backend container in restart loop, logs say `pydantic.ValidationError: SECRET_KEY too short`

Your `.env` has a `SECRET_KEY` shorter than 32 chars OR a known placeholder.

```bash
NEW_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))")
sed -i "s|^SECRET_KEY=.*|SECRET_KEY=${NEW_KEY}|" .env
docker compose up -d --force-recreate backend
```

If you'd already saved encrypted secrets in `module_configs` under the old (weak) `SECRET_KEY`, those secrets are now unreadable — see [configuration.md → Rotating SECRET_KEY](./configuration.md#rotating-secret_key).

### Backend logs say `CORS_ORIGINS=['*'] is unsafe`

You set `CORS_ORIGINS=["*"]` in `.env`. Replace with your portal's actual origin:

```
CORS_ORIGINS=["https://portal.your-company.com"]
```

The portal refuses `*` because cookies + wildcard CORS is a known browser-bypassable combination. Multiple origins are fine: `["https://a.example.com", "https://b.example.com"]`.

### `portal-worker-1` shows `(unhealthy)` after 90 seconds

If you've JUST started the stack, give it another 30 seconds — the worker's healthcheck is `arq --check WorkerSettings` which does Python imports + Redis dial (~6–10s) and runs every 30s, so the first probe takes a while.

If it's been > 2 minutes:

```bash
docker compose logs worker --tail=50
```

Common causes:
- Redis not reachable: `docker compose ps redis` — should be healthy
- arq import error: run `docker compose exec worker python -m scripts.qdrant_snapshot --help` — if it errors, the image is broken; rebuild with `docker compose build worker && docker compose up -d --force-recreate worker`

### `portal-postgres-1` healthy but backend can't connect

```
asyncpg.exceptions.InvalidPasswordError: password authentication failed for user "portal"
```

Your `POSTGRES_PASSWORD` in `.env` differs from what postgres was initialized with. Postgres only honors `POSTGRES_PASSWORD` on **first init** — subsequent password changes need to be done inside Postgres.

Two ways to fix:

**A. Reset Postgres entirely (deletes ALL portal data — only for fresh installs):**

```bash
docker compose down
docker volume rm portal_postgres_data
docker compose up -d
docker compose exec backend alembic upgrade head
```

**B. Update the Postgres user's password to match `.env`:**

```bash
docker compose exec -T postgres psql -U postgres -c "
  ALTER USER portal WITH PASSWORD 'WHATEVER_IS_IN_YOUR_ENV';
"
docker compose restart backend
```

### Frontend returns 502 / connection refused

```bash
docker compose ps frontend
```

If it's not "Up", something killed it. Logs:

```bash
docker compose logs frontend --tail=50
```

Most common cause: the SvelteKit dev server crashed because Vite couldn't reach the backend. Check that backend is up + healthy first.

If everything's running but `curl http://localhost:5173/` returns 502: restart frontend → `docker compose restart frontend && sleep 8`.

---

## Document upload + indexing

### Upload returns 413 "File exceeds 50 MB limit"

That's the configured cap. To raise it, edit `_MAX_UPLOAD_BYTES` in `backend/app/modules/ask_docs/routes.py`, then `docker compose up -d --force-recreate backend`.

Note that `pg_dump` includes the file metadata but uploads themselves live in the `portal_uploads` volume. Larger files = bigger backups proportionally.

### Upload returns 400 "Unsupported content type"

Allowed types: PDF, DOCX, TXT, MD. Hardcoded in `_ALLOWED_CONTENT_TYPES`. To add more (e.g., RTF, ODT), edit the set + restart backend. Note that the parser only knows how to extract text from the four allowed types today — adding a new content type requires also extending `parsers.py`.

### Document stuck in `pending` state

Worker isn't picking jobs up.

```bash
docker compose ps worker        # Should be (healthy)
docker compose logs worker --tail=50
```

Common causes:
- Worker container crashed: restart it (`docker compose restart worker`)
- Redis not reachable from worker: `docker compose exec worker redis-cli -h redis ping` — should return PONG

### Document moves to `failed` with `ParserError: Cannot extract text`

The file is unreadable as text:
- **Encrypted PDF** — unlock it first (`qpdf --decrypt --password=PWD in.pdf out.pdf`)
- **Scanned PDF without OCR** — run `ocrmypdf in.pdf out.pdf` first, then re-upload
- **Password-protected DOCX** — same idea; remove the password in Word first

### Document moves to `failed` with `nomic-embed-text not found`

The Ollama embeddings model isn't pulled.

```bash
docker compose exec ollama ollama pull nomic-embed-text
# Re-trigger indexing:
docker compose exec -T postgres psql -U portal -d portal -c "
  UPDATE ask_docs_documents
    SET status = 'pending'
    WHERE status = 'failed' AND error_message LIKE '%nomic-embed-text%';
"
```

### Document moves to `failed` with redacted error like `[REDACTED]: Connection refused`

Worker couldn't reach Ollama or Qdrant. The `[REDACTED]` is the secret-scrubber wiping potential auth tokens from the error string.

```bash
docker compose ps                       # Both ollama + qdrant should be healthy
docker compose exec worker curl http://ollama:11434/api/tags     # Should return JSON
docker compose exec worker curl http://qdrant:6333/collections    # Should return JSON
```

If those fail from inside the worker, the Docker network is broken — `docker compose down && docker compose up -d`.

---

## Chat failures

### Chat returns SSE event `{"type":"error","detail":"ANTHROPIC_API_KEY not configured"}`

The chat orchestrator looked for an Anthropic key and found neither a saved one (in `module_configs`) nor an env-var fallback (`ANTHROPIC_API_KEY` in `.env`).

Fix one of:
- Set `ANTHROPIC_API_KEY=sk-ant-...` in `.env` and `docker compose up -d --force-recreate backend`
- OR open `/admin/modules/ask-docs/config`, paste the key, save

### Chat returns SSE event with redacted `[REDACTED]: HTTP 401 from api.anthropic.com`

Your Anthropic key is rejected. Common causes:
- Key was revoked or expired — check the Anthropic console
- Key is for a different account than billed — check console
- Account has $0 credit balance — Anthropic returns 401 / 400 on this depending on the day. Add billing.

### Chat returns SSE event with redacted `[REDACTED]: Connection refused` (Ollama mode)

Your configured Ollama URL doesn't reach a running Ollama. Check:
- The URL in `/admin/modules/ask-docs/config` — is it reachable from the BACKEND container? (`docker compose exec backend curl <YOUR_URL>/api/tags`)
- The Ollama you're pointing at is actually serving (`docker compose exec ollama ollama list`)
- The model you specified is pulled into THAT Ollama (`docker compose exec ollama ollama list` should show your chat model)

### Chat answer is always "I don't have enough information to answer that question"

This is the hallucination guard firing. Two cases:

1. **Retrieval found nothing relevant.** Check:
   - Document is `indexed` (not `failed`/`pending`) on `/modules/ask-docs/library`
   - Try a question that's a near-verbatim match for content in the document — confirms the retrieval pipeline works
   - Enable the reranker in `/admin/modules/ask-docs/config` → Advanced

2. **LLM hallucinated and the post-processor refused to ship it.** Check the `/admin/modules/ask-docs` query log → click the failing query → look at "Cited sources" in the side panel. If it's empty BUT `tokens_used` is high, the LLM produced text without citing chunks (we replaced its output with the canonical "no info" message).

If the cited sources panel SHOWS chunks but the answer says "no info", the LLM is correctly recognizing the chunks don't actually answer the question. Try better-fitting source material.

### Chat is slow (> 10 seconds for first token)

Where the time goes:
- Embedding the query: ~50–100ms (local Ollama)
- Qdrant retrieval: ~10–50ms
- (If reranker enabled) cross-encoder: 50–200ms; FIRST chat after enabling adds 5–10s for model load
- LLM API roundtrip: 1–5s for sonnet-4-6 first token; longer for opus
- Network latency to api.anthropic.com: 50–200ms typical

If you're seeing 10+ seconds:
- Check `docker compose logs backend --tail=20 | grep duration_ms` for the orchestrator's recorded latency
- If `duration_ms` is < 5000 but you experience > 10s in the UI, the network path between your browser and the backend is slow — check Caddy / Cloudflare config
- If `duration_ms` IS > 10000, the LLM is genuinely slow — try a different model OR check Anthropic's status page

---

## Admin UI issues

### `/admin/modules/ask-docs/config` page crashes with `Cannot read properties of undefined (reading 'enabled')`

You're hitting the bug fixed in commit `186900c` — pre-P1.3b config row didn't have the `reranker` key. If you're on a portal version older than `0.5.0`:

```bash
git pull
docker compose up -d --force-recreate backend
```

The fix is server-side: `load_config` now merges schema defaults so missing fields appear with default values.

### Dashboard shows 0 docs / 0 queries despite knowing there are some

Your session probably timed out and the page is rendering against a 401. Hard-refresh + log back in.

If logged in fresh AND still showing zeros: the dashboard polls `/api/admin/modules/ask-docs/dashboard` — open the browser dev tools network tab and check what that endpoint actually returns.

### "Configure →" / "Dashboard →" links don't appear on the modules catalog

The links only appear when the module is `enabled`. Visit `/admin/modules` and check that Ask Docs has the "Active" badge (vs the "Request" button). If not, click "Enable".

---

## Backup / restore

### `bash scripts/backup.sh` errors with `ERROR: portal-backend is not running`

```bash
docker compose ps           # Make sure backend, postgres, qdrant are all "Up"
docker compose up -d        # If anything's down
```

Then re-run backup.

### `bash scripts/restore.sh ARCHIVE.tar.gz` errors with `ERROR: ARCHIVE.tar.gz is not a valid tar.gz`

The integrity preflight fails. Either:
- File got corrupted in transit — re-download from the source
- Wrong file path
- File was encrypted (e.g., GPG-wrapped) — decrypt first: `gpg --decrypt ARCHIVE.tar.gz.gpg > ARCHIVE.tar.gz`

### Restore says `DecryptionError` after applying

You restored the Postgres dump but kept your local `.env` with a different `SECRET_KEY`. The encrypted secrets in `module_configs` can't be decrypted.

Fix:

```bash
docker compose exec -T postgres psql -U portal -d portal -c "DELETE FROM module_configs;"
docker compose up -d --force-recreate backend
# Re-enter Anthropic key via /admin/modules/ask-docs/config
```

OR re-run restore and answer **yes** to "Apply backup .env" — that gives you the matching `SECRET_KEY`.

### "Backup did not become healthy in 60s" after restore

```bash
docker compose logs --tail=50 backend       # Read the actual error
```

The script's exit-1 message also dumps the last 50 lines. Common causes:
- `SECRET_KEY` mismatch (above)
- Migration drift (backup from older portal, current portal has newer schema): `docker compose exec backend alembic upgrade head`
- Pg_restore left tables but data is corrupted: re-run restore

Both `pg_restore --clean --if-exists` and the Qdrant snapshot upload (`?priority=snapshot`) are idempotent. Re-running the restore is always safe.

---

## Phone-home / Operator Console

### Logs say `OC heartbeat response missing 'actions' key — treating as empty`

The OC server returned a 200 with an unexpected JSON shape. Check:
- Is `OC_URL` pointing at a real Hoelscher Automation OC instance? (Not a misconfigured proxy?)
- Is the OC service version compatible with your portal version?

This is a warning, not a fatal error — phone-home keeps running, but no actions get applied.

### Logs say `Unknown module_key: 'foo'`

The OC sent an action for a module the portal doesn't know about (the `REGISTRY` enum). Either:
- The module is genuinely new and your portal predates it — upgrade
- The OC has stale state and is retrying an old action — wait for it to give up

The portal correctly refuses the action and acks the OC with `result: error`.

---

## Healthchecks

### `docker compose ps` shows `(unhealthy)` for a service that seems fine

Check what the healthcheck is:

```bash
docker inspect portal-XXX-1 --format '{{json .Config.Healthcheck}}' | python3 -m json.tool
```

Then check what it's actually returning:

```bash
docker inspect portal-XXX-1 --format '{{json .State.Health.Log}}' | python3 -m json.tool | tail -50
```

Common gotcha: the worker's healthcheck is `arq --check WorkerSettings` which takes 6–10 seconds. If `interval: 30s` and `timeout: 5s`, every probe times out — that's a bug we hit in P1.5 (fixed at commit `7491227`). If you're seeing this on a recent install, your portal version may be older than the fix.

---

## Still stuck

Collect the diagnostic bundle from [install.md → Getting help](./install.md#getting-help) and send it to the install team along with:
- A description of what you tried
- The exact symptom (error message verbatim, screenshot if it's a UI issue)
- Recent git log: `git log --oneline -10`

Most issues we've seen in the field have been one of:
- `.env` misconfiguration (validators catch most of these now)
- Container was rebuilt but not recreated (`docker compose up -d --force-recreate <service>` after `docker compose build`)
- Stale Docker network state (`docker compose down && docker compose up -d` resolves)
- Missing OS package in older Ubuntu installs (e.g., `python3` for the host scripts)

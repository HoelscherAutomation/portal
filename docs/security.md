# Security & Threat Model

What the portal protects against, what it doesn't, and what you (the operator) need to do to keep it safe.

This is for the IT person responsible for the install, not for end users.

---

## Threat model summary

The portal is designed for **single-tenant, self-hosted, semi-trusted environment** use:

- **One customer** per install (no multi-tenant isolation in the schema)
- **Self-hosted** — runs on customer-controlled hardware, not SaaS
- **Semi-trusted users** — the people who can log in are employees of the customer; not random internet strangers
- **Trusted operator** — the IT person installing + maintaining the portal has full host access

What this means in practice:

| Threat | In scope | Out of scope |
|---|---|---|
| Random internet attacker hitting the portal directly | ✓ — Caddy IP allowlist or VPN-only access expected | — |
| Authenticated employee misusing their access (e.g., reading docs they shouldn't) | Partially — see "Access control" below | Per-doc ACLs not built (every authenticated user sees every Ask Docs upload) |
| Compromised admin account | ✓ — admin can reconfigure modules, but encryption key isn't admin-accessible | — |
| Compromised host root | Out of scope — root has access to .env, DB, Qdrant snapshot, everything | — |
| Compromised LLM provider (Anthropic) | Out of scope — you're trusting their API; switch to Ollama mode if this matters | — |
| Backup file leak | ✓ — backup is mode 0600, file IS a credential, documented loudly | Operator must encrypt at rest themselves |
| Data exfiltration via Ask Docs queries | Out of scope today — any authenticated user can query any uploaded doc | — |
| Supply chain (Docker images, Python deps) | Partially — versions pinned, but no SBOM / signing | Out of scope for transitive deps |

If your use case extends beyond this (multi-tenant, untrusted users, high-stakes data), the portal in its current form is **not** the right fit. Talk to Hoelscher Automation about a custom deployment.

---

## What's protected

### Authentication

- **Cookie-based sessions** via `fastapi-users` with JWT strategy
- **HttpOnly cookies** so JS can't read the session token
- **`SameSite=lax`** so cross-origin POSTs without an Origin header are blocked
- **`COOKIE_SECURE=true`** in production — cookie only sent over HTTPS
- **Argon2** password hashing (via `argon2-cffi`) — slow + memory-hard
- **No password reset email flow** — admin resets passwords manually via `python -m scripts.create_admin` or by querying Postgres. (Email-based reset is on the roadmap.)

### Authorization

Three trust tiers:

1. **Public** — `/api/health`, login routes, static frontend assets
2. **Authenticated user** — `/api/me`, `/api/modules` (read-only), `/modules/ask-docs/*` (chat + library + upload + delete-own)
3. **Superuser** — everything under `/admin/*` and `/api/admin/*` (branding, module enablement, LLM config, dashboard, query log)

**Document delete** is gated to "uploader OR superuser" — other authenticated users get 403 even if they can READ the document via the library.

### Encryption at rest

- **Module config secrets** (Anthropic API key today; Voyage / Hoelscher proxy keys in future) stored in `module_configs.config` JSONB column
- **Encryption:** Fernet symmetric (AES-128-CBC + HMAC-SHA256)
- **Key derivation:** HKDF-SHA256 from `SECRET_KEY` env var, with domain-separated salt + info strings so the same `SECRET_KEY` derives different keys for sessions vs Fernet
- **No plaintext in DB:** even an admin with `SELECT * FROM module_configs` only sees `{"_encrypted": true, "value": "<ciphertext>"}` markers
- **API responses:** secrets always redacted to `{"_set": true|false}` markers — never plaintext over the wire

What's NOT encrypted at rest:
- Postgres data files (use disk-level encryption — LUKS / dm-crypt — if you need this)
- Qdrant collection data (same)
- Uploaded files in the `portal_uploads` volume (same)

### Backup integrity + secrets

- Backup tar.gz produced with `chmod 600` — owner-only readable
- `MANIFEST.json` carries sha256 for each component; restore validates before applying
- Restore explicitly does NOT auto-apply the backup's `.env` (defaults to keeping host's current .env to avoid accidental cross-host SECRET_KEY swaps)
- Probe / chat error messages run through `_scrub_secrets` to redact `sk-...`, `pa-...`, `Bearer ...`, `Basic ...` patterns before surfacing to UI/logs

### Input validation

- File uploads: MIME type + size cap (50 MB default)
- File paths: `PurePosixPath(filename).name` strips directory components (no path traversal)
- SQL: SQLAlchemy ORM parameterizes everything (no raw string interpolation)
- HTML: Svelte escapes by default; no `{@html}` usage
- LLM prompt injection: the system prompt explicitly instructs `[N]` citations + "no info" fallback for unanswerable questions; the post-processor enforces both (hallucination guard)

### Phone-home / OC trust

If `OC_URL` is set:
- Portal sends heartbeats with portal version + enabled modules + pending requests
- Portal RECEIVES action queue from OC (enable_module, disable_module, mark_request_fulfilled)
- Actions are validated against the portal's module REGISTRY before applying — a compromised OC cannot inject arbitrary module_keys
- All traffic over HTTPS with `Bearer OC_TOKEN` auth

You opt-in by setting `OC_URL` + `OC_TOKEN`. Without those, the loop never starts.

---

## What you need to do

### At install

1. **Generate strong `SECRET_KEY`** — use `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`. The portal validator refuses < 32 chars or known placeholders.
2. **Generate strong `POSTGRES_PASSWORD`** — same generator.
3. **Set `CORS_ORIGINS` to your portal's actual origin** — never `["*"]`. Validator refuses wildcards.
4. **`COOKIE_SECURE=true` in production** — only meaningful behind HTTPS.
5. **Put HTTPS in front** — Caddy + Let's Encrypt is the easy path; `caddy.com/docs` walks through it.
6. **Restrict access** — for non-public installs, use Caddy's `@allowed remote_ip` directive to allow only your office IP range / VPN range. See [Restricting access](#restricting-access) below.

### Ongoing

1. **Backup the install regularly** (cron) AND **encrypt the backup files at rest** AND **keep them off-host**. See [backup-restore.md](./backup-restore.md).
2. **Monitor the dashboard's cost estimate** weekly — sudden spikes can signal misuse or LLM API issues.
3. **Update the portal periodically** — `git pull && docker compose pull && docker compose up -d` then `docker compose exec backend alembic upgrade head`. See [upgrade.md](./upgrade.md) (TODO).
4. **Rotate `SECRET_KEY`** if you suspect compromise (e.g., backup file leaked, departing employee with access). See [configuration.md → Rotating SECRET_KEY](./configuration.md#rotating-secret_key).
5. **Audit users periodically** — `docker compose exec postgres psql -U portal -d portal -c "SELECT email, is_superuser, is_active FROM users;"`. There's no UI for user management today.

### When something looks wrong

- **Suspicious queries** in the dashboard's query log → click the row to see the cited sources. If they don't match the question, the user might be probing for sensitive content.
- **Unusual login activity** — no audit log built today. For high-security needs, add Caddy access logs + parse them.
- **Backup file accessed by someone unexpected** — treat as a full credentials compromise. Rotate `SECRET_KEY`, `POSTGRES_PASSWORD`, `ANTHROPIC_API_KEY` simultaneously. Re-issue admin passwords. The encrypted module configs become unreadable; re-enter them.

---

## Restricting access

For non-public installs (most customers), restrict to office network + VPN.

Add to your Caddyfile:

```caddyfile
portal.your-company.com {
    # Allow only office network + Tailscale + your VPN range
    @allowed remote_ip 192.168.0.0/16 100.64.0.0/10 10.0.0.0/8

    # Default-deny everything else
    handle @allowed {
        reverse_proxy /api/* localhost:8000
        reverse_proxy localhost:5173
    }

    handle {
        respond "Access denied" 403
    }
}
```

Replace the IP ranges with what's actually in scope for your network.

If you ALSO want public access for some routes (e.g., a public health-check probe from an external monitor), break those out:

```caddyfile
portal.your-company.com {
    handle /api/health {
        reverse_proxy localhost:8000
    }
    handle * {
        @allowed remote_ip 192.168.0.0/16 100.64.0.0/10
        handle @allowed {
            reverse_proxy /api/* localhost:8000
            reverse_proxy localhost:5173
        }
        handle {
            respond "Access denied" 403
        }
    }
}
```

`/api/health` returns only `{"status": "ok"}` — no internal state — so it's safe to expose unauth.

---

## User registration

By default, **anyone who can reach `/register` can create an account.** This is fine if the portal is behind a Caddy IP allowlist (only employees can reach it anyway).

For internet-facing installs, lock down `/register`:

**Option A: Block at Caddy level**

```caddyfile
handle /register {
    respond "Registration is disabled. Contact your admin." 403
}
```

**Option B: Disable the route in the backend**

Edit `backend/app/main.py` to remove the `/register` router include. Restart backend. Admins create users via `python -m scripts.create_admin` only.

A first-class "registration toggle" config is on the roadmap.

---

## What's NOT yet built

Honest list of security features that aren't shipping today:

- **Audit log** — no record of who did what when (admins changing config, users uploading docs, etc.). All changes ARE recorded in DB row timestamps but not in a unified log.
- **Per-doc ACLs** — every authenticated user sees every Ask Docs upload. If you have docs that some employees shouldn't read, don't put them in Ask Docs today.
- **Rate limiting** — no built-in throttle on login attempts, chat queries, uploads. Add Caddy rate limiting if you need it.
- **2FA / MFA** — not built. fastapi-users supports it via plugin; not wired in.
- **Email verification on registration** — fastapi-users supports it; we haven't enabled it (would need an SMTP provider).
- **Password reset email flow** — same.
- **Session revocation** — no admin UI to "log out user X." Workaround: rotate `SECRET_KEY` (logs everyone out + re-encrypts secrets).
- **CSP / HSTS headers** — set these at the Caddy layer, not in FastAPI.
- **Dependency / image vulnerability scanning** — no built-in. Run `trivy image portal-backend` periodically.

If any of these block your use case, file a request — most are 1–3 day adds.

---

## Quick security checklist

Before going live with a customer install:

- [ ] `SECRET_KEY` is 32+ chars from `secrets.token_urlsafe(48)` (NOT the placeholder)
- [ ] `POSTGRES_PASSWORD` is 24+ chars from a generator (NOT a hand-typed value)
- [ ] `.env` has `chmod 600` and is not committed to git
- [ ] `CORS_ORIGINS` set to the actual portal origin, not `["*"]`
- [ ] `COOKIE_SECURE=true`
- [ ] HTTPS in front (Caddy + Let's Encrypt or equivalent)
- [ ] IP allowlist on Caddy if not for public access
- [ ] First admin account uses a strong password
- [ ] `/register` lockdown decided (allow if behind allowlist, deny otherwise)
- [ ] Backup script set up + tested + offsite-copied + encrypted at rest
- [ ] Operator (you) understands the backup file IS A CREDENTIAL
- [ ] LLM mode chosen and live-tested (`/admin/modules/ask-docs/config` Test button)

---

## See also

- [install.md](./install.md) — the production deployment section
- [configuration.md](./configuration.md) — every env var + rotation procedures
- [backup-restore.md](./backup-restore.md) — backup file handling
- [troubleshooting.md](./troubleshooting.md) — auth / cors / cookie failures

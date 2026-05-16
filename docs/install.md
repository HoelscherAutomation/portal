# Install Guide

This guide takes you from a fresh Linux server to a running Hoelscher Employee Portal in about 30 minutes (mostly waiting on Docker image pulls and the first Ollama model download).

If anything in here is wrong or unclear, the install team wants to know — see "Getting help" at the bottom.

---

## What you'll end up with

A self-hosted employee portal accessible at a URL you control (e.g. `portal.your-company.com`), with:

- An **Ask Docs** module live by default — upload PDFs/DOCX/TXT/MD, employees ask questions, get cited answers from your documents
- An **admin section** for branding (logo, color, welcome message), enabling additional modules, configuring the LLM backend, and viewing usage stats
- A **backup/restore** workflow so you can move the install or recover from disaster

Everything runs in Docker on hardware you control. Documents never leave your server. The only outbound traffic by default is to Anthropic for chat completions (and only if you choose Anthropic as the LLM mode — Ollama mode keeps everything local).

---

## Hardware requirements

| Resource | Minimum | Recommended |
|---|---|---|
| CPU | 4 cores | 8+ cores |
| RAM | 8 GB | 16 GB |
| Disk | 40 GB SSD | 100 GB SSD |
| Network | Reachable from your office network or VPN | Plus Cloudflare/Caddy for HTTPS termination |

**Notes:**
- The Ollama embeddings model (`nomic-embed-text`, ~300 MB) downloads on first start
- With reranking enabled (optional, off by default), an additional ~80 MB ONNX model downloads on first chat
- Disk grows with documents you upload + the Postgres + Qdrant indexes (rule of thumb: budget 3× your raw document size)
- Memory grows with concurrent chat sessions; 8 GB handles ~5 simultaneous chats comfortably

---

## OS prerequisites

This guide assumes Ubuntu 22.04 or 24.04. Other Debian-based distros work the same. RHEL/Fedora users will need to translate `apt` → `dnf`.

> **On a minimal cloud image?** Some VPS providers ship "minimal" Ubuntu variants without `curl`. If `curl --version` fails, install it first: `sudo apt update && sudo apt install -y curl`.

### 1. Install Docker

```bash
# Per Docker's official install instructions (verify at docs.docker.com)
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
# Log out and back in for the group change to take effect
```

Verify:

```bash
docker --version          # 24.x or newer
docker compose version    # 2.x or newer
```

### 2. Install git

```bash
sudo apt update && sudo apt install -y git
```

That's it for OS prereqs. Everything else runs in containers.

---

## Get the portal code

The portal source is hosted at [github.com/HoelscherAutomation/portal](https://github.com/HoelscherAutomation/portal). Clone it with:

```bash
git clone https://github.com/HoelscherAutomation/portal.git
cd portal
```

This is the same repository you'll pull updates from later — see [upgrade.md](./upgrade.md) for the standard `git pull` upgrade flow once you're running.

> **Note for developers:** the file `docker-compose.override.yml.example` is provided as a starting point if you want to enable bind-mounted source + auto-reload for local development. Operators running a production install should leave it alone — Docker Compose only applies an override file if it's named `docker-compose.override.yml` (no `.example`).

---

## Configure secrets — the only manual step

The portal won't start without a valid `.env`. Copy the template and fill in the required values:

```bash
cp .env.example .env
```

Open `.env` in your editor. **Three values are required**, the rest have safe defaults:

### `SECRET_KEY` (required, no default)

This signs session cookies AND derives the encryption key for stored API keys (Anthropic key in `module_configs`). The portal **refuses to start** with a missing, short (< 32 chars), or placeholder value.

Generate a strong one:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Paste the result into `.env`:

```
SECRET_KEY=<the-output-of-the-command-above>
```

⚠️ **Treat this value like a password.** If you ever rotate `SECRET_KEY`, all encrypted API keys in `module_configs` become unreadable and must be re-entered. The `.env` file should be `chmod 600` and never committed to git (it's already in `.gitignore`).

### `POSTGRES_PASSWORD` (required, no safe default)

Generate one:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(24))"
```

Set in `.env`:

```
POSTGRES_PASSWORD=<the-output>
```

### `ANTHROPIC_API_KEY` (required for chat in default Anthropic mode)

If you want to use Anthropic's Claude as the chat backend (the default — most accurate, costs ~$0.005 per chat query):

1. Create an account at https://console.anthropic.com
2. Go to API Keys, create a new key starting with `sk-ant-...`
3. Add billing — Anthropic doesn't give free tier; you'll need to add a payment method or buy credits
4. Paste in `.env`:

```
ANTHROPIC_API_KEY=sk-ant-api03-...
```

If you'd rather run a local LLM via Ollama (no per-query cost, but slower + lower quality on most hardware), you can leave this empty for now and switch modes from the admin UI after first install. See [ask-docs.md](./ask-docs.md#switching-llm-modes).

### Other settings (optional, defaults are fine for most installs)

```
BACKEND_PORT=8000           # Local port the FastAPI backend listens on
COOKIE_SECURE=false         # Set to true once you put HTTPS in front (see "Production" below)
CORS_ORIGINS=["http://localhost:5173"]  # Replace with your portal's external URL when behind HTTPS
PORTAL_VERSION=0.7.0        # Used in backup manifests; advance when you upgrade
PUBLIC_API_URL=http://localhost:8000    # The URL the BROWSER will use to reach the backend
```

⚠️ **Never set `CORS_ORIGINS=["*"]`** — the portal refuses to start with a wildcard since cookies + wildcard CORS is a known browser-bypassable combination.

⚠️ **`PUBLIC_API_URL` matters more than it looks.** This is the backend URL the *browser's JavaScript* will call — it's read by the frontend and passed to the user's browser. The default `http://localhost:8000` only works when the user opens the portal *on the server itself*. If users access the portal from their own laptops (the normal case), `PUBLIC_API_URL` must be set to a URL their browser can actually reach — e.g., your server's IP for LAN-only installs (`http://192.168.10.20:8000`) or your portal's HTTPS domain for production (`https://portal.your-company.com/api`, with a Caddy reverse proxy — see "Production deployment" below). After changing `PUBLIC_API_URL`, recreate the frontend: `docker compose up -d --force-recreate frontend`.

---

## First boot

```bash
docker compose up -d
```

This pulls images (~2 GB total) and starts 7 containers:

- `portal-postgres-1` — Postgres 16
- `portal-redis-1` — Redis (used by the background worker)
- `portal-qdrant-1` — vector store
- `portal-ollama-1` — local LLM runtime (used for embeddings; optional for chat)
- `portal-backend-1` — FastAPI backend
- `portal-frontend-1` — SvelteKit frontend
- `portal-worker-1` — arq background worker (indexing jobs)

First boot takes ~60 seconds. Watch progress:

```bash
docker compose ps
```

Wait until all 7 services show `(healthy)` in the STATUS column. Most services come up within ~30 seconds; the slowest is the worker (its arq healthcheck has a 90-second `start_period` to give Python imports + the first Redis dial time to complete on slow disks). On a normal install you'll see `(healthy)` on the worker between 30 and 90 seconds in.

If anything shows `(unhealthy)` after 2 minutes, see [troubleshooting.md](./troubleshooting.md#first-boot-failures).

### Apply database migrations

```bash
docker compose exec backend alembic upgrade head
```

Output starts with `INFO [alembic.runtime.migration] Will assume transactional DDL.`, followed by one `Running upgrade ... -> ...` line per migration. The last `Running upgrade` line is the most recent migration applied — for a fresh install on v0.6.x that's `... -> 72aa95c0b171, add ask_docs_migration_state`.

### Pull the embeddings model

The first document you upload will trigger this automatically, but you can warm the cache now:

```bash
docker compose exec ollama ollama pull nomic-embed-text
```

~300 MB download. Takes ~30 seconds on broadband.

### Create your first admin user

```bash
docker compose exec backend python -m scripts.create_admin
```

Interactive prompt:

```
Email: you@your-company.com
Password: <enter a strong password>
Confirm: <enter again>
✓ Created admin user with superuser privileges: you@your-company.com (id=1)
```

This user can log in to the portal AND access the `/admin/*` routes.

---

## Verify it works

### 1. Open the portal

Navigate to `http://localhost:5173` in a browser (or your server's IP if you're SSH'd in: `http://your-server-ip:5173`).

You should see a login page with a "Welcome back" heading.

### 2. Log in

Use the admin credentials you just created. After login you should land on the home page with the portal's default branding.

### 3. Check the admin section

Click the avatar / superuser indicator in the top right and visit `/admin/branding`. You can change the company name, primary color, welcome message, and upload a logo here. Your changes are live immediately.

### 4. Enable the Ask Docs module

Visit `/admin/modules`. You should see 7 module cards. **Ask Docs** is set to "Live" by default but starts disabled — click "Enable" to flip it on.

(You'll also see "Configure →" and "Dashboard →" links appear once it's enabled. We'll use those next.)

### 5. Configure the LLM backend (only if not using env-var Anthropic key)

If you set `ANTHROPIC_API_KEY` in `.env`, you can skip this — the chat will use the env key as a fallback.

Otherwise, click "Configure →" on the Ask Docs card. Pick a mode (Anthropic or Ollama), fill in the settings, click "Test [Mode]" to verify the config works, then "Save changes."

See [ask-docs.md](./ask-docs.md#configuring-the-llm-backend) for details on each mode.

### 6. Upload your first document

Navigate to `/modules/ask-docs/library` (or click "Ask Docs" in the top nav after enablement). Drop a PDF, DOCX, TXT, or MD file in the upload area. It transitions through `pending → indexing → indexed` over a few seconds.

### 7. Ask your first question

Click "Ask Docs" in the top nav (the chat page, `/modules/ask-docs`). Type a question about something you'd expect to find in the document you uploaded. Watch the answer stream in. Click any `[1]` citation pill to see the source chunk.

If you see `"I don't have enough information to answer that question"` for a question you know the document covers — see [troubleshooting.md](./troubleshooting.md#ask-docs-says-no-information).

---

## Production deployment

The dev install above runs HTTP-only on `localhost:5173`. For a real customer-facing install you want HTTPS termination + a real domain.

The recommended setup:

1. **Domain** — point a DNS A record at your server (`portal.your-company.com → your-server-ip`)
2. **TLS** — put [Caddy](https://caddyserver.com/) in front of the backend (Caddy auto-provisions Let's Encrypt certs)
3. **`.env` updates** for production:
   ```
   COOKIE_SECURE=true
   CORS_ORIGINS=["https://portal.your-company.com"]
   PUBLIC_API_URL=https://portal.your-company.com/api
   ```
4. **Restart** the affected services so the new env takes effect:
   ```bash
   docker compose up -d --force-recreate backend frontend
   ```
   (Frontend must restart too — `PUBLIC_API_URL` is read at container start.)

A minimal Caddyfile:

```caddyfile
portal.your-company.com {
    reverse_proxy /api/* localhost:8000
    reverse_proxy /uploads/* localhost:8000
    reverse_proxy localhost:5173
}
```

Run Caddy with `caddy run --config Caddyfile` (or as a systemd service — see Caddy docs).

For LAN/VPN-only access (recommended for non-public installs), add an IP allowlist directive — see [security.md](./security.md#restricting-access).

---

## What to do next

- [first-run.md](./first-run.md) — walks you through your first 30 minutes after install (branding, enabling modules, uploading docs, asking questions, granting other admins)
- [configuration.md](./configuration.md) — every `.env` variable explained
- [backup-restore.md](./backup-restore.md) — set up your first backup before you have data you'd hate to lose
- [troubleshooting.md](./troubleshooting.md) — when things go sideways

---

## Getting help

If the install fails, please collect the following before asking for help:

```bash
# What state is the stack in?
docker compose ps

# Recent logs from each service
docker compose logs --tail=100 backend > /tmp/backend.log
docker compose logs --tail=100 worker  > /tmp/worker.log
docker compose logs --tail=100 frontend > /tmp/frontend.log

# Your docker + compose version
docker --version
docker compose version

# Your .env (redact SECRET_KEY, POSTGRES_PASSWORD, ANTHROPIC_API_KEY values first!)
cat .env | sed 's/=.*$/=<REDACTED>/'
```

Send the four files (logs + version + redacted .env) to whomever is supporting your install. **Do not send the unredacted `.env`** — it contains every credential the portal uses.

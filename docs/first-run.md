# First-Run Walkthrough

Your first 30 minutes after the install completes. By the end you'll have a branded portal, the Ask Docs module live, your first document indexed, and your first cited answer streaming from the LLM.

Assumes you've completed [install.md](./install.md) and have an admin user.

---

## 1. Log in (1 min)

Open `http://localhost:5173` (or your production URL). You'll see a "Welcome back" login form.

Enter the admin credentials you created at the end of the install.

You should land on the home page — it's intentionally minimal at this point. The next few steps make it yours.

---

## 2. Set the branding (3 min)

Click your avatar in the top right → **Admin → Branding** (or navigate directly to `/admin/branding`).

Three things to change:

- **Company name** — appears in the top header next to the logo. Defaults to "Hoelscher Employee Portal" if you leave it blank.
- **Primary color** — the accent color used for links, buttons, and highlights. Pick a color that matches your brand (hex code or color picker).
- **Welcome message** — shown on the authenticated home page. A sentence or two; HTML not supported.

Optionally upload a **logo**:
- PNG, JPEG, or SVG; ≤ 2 MB
- Square or wide-rectangle works best
- Replaces the default text logo in the header

Click **Save**. Your changes are live immediately — refresh any open tab to see them.

---

## 3. Enable the Ask Docs module (1 min)

Visit **Admin → Modules** (`/admin/modules`). You'll see 7 module cards:

| Module | Status | What it does |
|---|---|---|
| **Ask Docs** | Live | RAG-backed chat over your uploaded documents |
| Announcements | Preview | Company-wide announcements (not yet built) |
| Expense Reports | Preview | Submit + approve expenses (not yet built) |
| HR Documents | Preview | Read-only HR policy library (not yet built) |
| Onboarding | Preview | New-hire checklists (not yet built) |
| Time Off Requests | Preview | PTO request workflow (not yet built) |
| Workplace Directory | Preview | Employee org chart (not yet built) |

Only **Ask Docs** is shipping today. Click **Enable** on its card.

After enablement, two new links appear on the card:
- **Dashboard →** — admin dashboard for the module (covered in [admin-dashboard.md](./admin-dashboard.md))
- **Configure →** — LLM mode + reranker settings (covered in [ask-docs.md](./ask-docs.md#configuring-the-llm-backend))

---

## 4. Configure the LLM backend (5 min)

If you set `ANTHROPIC_API_KEY` in your `.env` and that's the LLM you want, you can **skip this step** — the chat will work using the env-var key as a fallback.

Otherwise, click **Configure →** on the Ask Docs card to land at `/admin/modules/ask-docs/config`.

You see three radio options under "Active mode":

- **Anthropic (cloud)** — Claude Sonnet 4.6 via api.anthropic.com. Highest quality. ~$0.005 per chat. Customer admin pastes their own API key.
- **BYO Ollama (self-hosted)** — Point at any Ollama server (could be the in-portal `ollama` container, a separate GPU box, or a colleague's). Free per-query. Quality depends on the model you load.
- **Hoelscher proxy** — Coming soon (managed inference billed by Hoelscher Automation).

Pick a mode, fill in the per-mode settings, click **Test Anthropic** (or Ollama). A green "OK · 423ms" or red error appears next to the button.

When the test passes, click **Save changes**. The next chat query will use the saved config.

Detailed setup for each mode lives in [ask-docs.md](./ask-docs.md#configuring-the-llm-backend).

### Optional: enable cross-encoder reranking

In the **Advanced** section near the bottom of the config page, there's a single checkbox for **Cross-encoder reranking**.

When on:
- Chat retrieves top-24 candidates from Qdrant (vs the default top-8)
- A small ONNX model scores each candidate against the question
- Top-8 by score get sent to the LLM

Quality bump: noticeable with 50+ chunks indexed; marginal with smaller corpora. Cost: ~50–200ms per query, plus a one-time ~80 MB model download on the first chat after enabling.

Default off. Turn on once you're past the "does this work at all" stage.

---

## 5. Upload your first document (2 min)

Click **Ask Docs** in the top nav, then the **Library** sub-link (`/modules/ask-docs/library`).

Click the upload area (or drag-and-drop). Supported types:
- PDF (`.pdf`)
- Word (`.docx`)
- Plain text (`.txt`)
- Markdown (`.md`)

Max 50 MB per file. Uploads run in three states:

- **pending** — file received, waiting for the worker
- **indexing** — worker is parsing → chunking → embedding (a few seconds for small docs, up to a minute for hundreds of pages)
- **indexed** — vectors written to Qdrant, ready for chat

The library auto-refreshes every 3 seconds. Once status flips to **indexed**, the document is searchable.

If status flips to **failed**, hover for the error message. Common causes:
- Encrypted/password-protected PDFs (we can't decrypt them)
- Scanned PDFs without OCR (no extractable text)
- DOCX with embedded media that's larger than the 50 MB cap

---

## 6. Ask your first question (1 min)

Click **Ask Docs** in the top nav. The chat page (`/modules/ask-docs`) opens with an empty conversation.

Type a question that the document you uploaded should be able to answer. Hit Enter (or click Ask).

Within ~3 seconds you should see:

- "Sources" event flashes (the chunks Qdrant returned)
- Tokens stream into the answer area as Claude (or your chosen LLM) writes
- **`[1]`, `[2]` citation pills** appear inline as the answer references sources
- A **final** event with the complete answer + the citation list

Click any `[N]` pill — a side panel slides in showing the cited source: filename, page number, and the actual chunk content. This is how you verify the LLM is grounding answers in real document content (not making things up).

If the answer says **"I don't have enough information to answer that question"** — that's the hallucination guard firing. The retrieval found nothing relevant OR the LLM correctly recognized that the available chunks don't address your question. Try a different question or upload more relevant documents.

---

## 7. Check the dashboard (3 min)

Visit **Admin → Modules → Ask Docs → Dashboard** (`/admin/modules/ask-docs`). You'll see:

- **Documents** card — total count + indexed count
- **Queries (30d)** card — count + avg/p95 latency
- **Tokens (30d)** card — total tokens consumed
- **Estimated cost (30d)** card — hardcoded pricing × tokens. Hover the card for the "prices as of YYYY-MM-DD" disclaimer.
- **Token usage chart** — daily bars, last 30 days
- **Mode breakdown** — queries + tokens per LLM mode
- **Document status** — indexed / indexing / pending / failed counts
- **Recent queries** — last 100 queries; click any row → side panel with full question, answer, and cited sources

Auto-polls every 30 seconds. The "last update HH:MM" timestamp confirms it's refreshing.

Detail in [admin-dashboard.md](./admin-dashboard.md).

---

## 8. Take your first backup (5 min)

Don't skip this. Even with one indexed document and a handful of queries, get familiar with the backup workflow now — before you have data you'd hate to lose.

From the repo root on your server:

```bash
bash scripts/backup.sh --output ~/portal-backups
```

You'll get a tar.gz file like `portal-backup-2026-05-10T19-00-00Z.tar.gz` (~64 KB for a fresh install, grows with documents + queries). Owner-readable only (mode 0600).

⚠️ **The backup file IS A CREDENTIAL.** It contains your `.env` (with `SECRET_KEY` and `ANTHROPIC_API_KEY`), the Postgres dump (with Fernet-encrypted module configs), and the Qdrant snapshot. Store it encrypted at rest. Don't email it. Don't put it in shared cloud storage without encryption.

Restore is symmetric: `bash scripts/restore.sh path/to/backup.tar.gz`. Two confirmation prompts before any destructive action; `--yes` skips them for cron automation.

Full backup/restore semantics: [backup-restore.md](./backup-restore.md).

---

## 9. Add other admins (2 min)

Right now there's only your account. To add a colleague:

```bash
docker compose exec backend python -m scripts.create_admin
```

This creates another superuser. There's no UI for user management yet (it's on the roadmap). For non-admin accounts, employees register via `/register` — but that flow is currently open registration, so:

- For internal-only deployments behind a VPN/IP allowlist: open registration is fine
- For anything internet-facing: lock down `/register` first (see [security.md](./security.md#user-registration))

---

## 10. (Optional) Set up production HTTPS

If your install is behind your office's network only and you're OK with HTTP, skip this.

Otherwise: see [install.md → Production deployment](./install.md#production-deployment) for the Caddy setup, and update `.env`:

```
COOKIE_SECURE=true
CORS_ORIGINS=["https://portal.your-company.com"]
```

Then:

```bash
docker compose up -d --force-recreate backend
```

---

## What's next

You now have a working install. Keep these in mind as you ramp up:

- **Documents:** more = better answers. Upload your handbook, policies, FAQ, onboarding materials, etc. The LLM grounds every answer in the chunks Qdrant retrieves; richer corpus = richer answers.
- **Costs:** watch the dashboard's 30d cost estimate weekly. If it's growing faster than expected, you can switch to Ollama mode (free per query) or add a `ASK_DOCS_MAX_ANSWER_TOKENS` cap.
- **Backups:** automate them. A simple cron entry: `0 3 * * * cd /path/to/portal && bash scripts/backup.sh --output /var/backups/portal/ 2>&1 | logger -t portal-backup`. Then offsite-copy them periodically.
- **Updates:** see [upgrade.md](./upgrade.md) for the `git pull` + migration workflow.

If anything's confusing, the docs index is at [index.md](./index.md) — every how-to lives there.

# Hoelscher Employee Portal — Documentation

Operator + admin documentation for the Hoelscher Employee Portal. Designed for the IT person responsible for installing, configuring, and maintaining the portal at a customer site.

End-user documentation (for employees who just want to use Ask Docs to find answers in company documents) lives under [end-user/](./end-user/) — TODO.

---

## Setup (do these in order, once per install)

1. **[install.md](./install.md)** — bare metal → running portal in ~30 minutes. Hardware requirements, Docker setup, `.env` configuration, first boot, create admin, verify.
2. **[first-run.md](./first-run.md)** — your first 30 minutes after install. Branding, enable modules, configure LLM, upload first document, ask first question, take first backup.
3. **[security.md](./security.md)** — pre-go-live checklist. Threat model, what's protected, what isn't, what you need to do.

## Day-to-day operation

- **[ask-docs.md](./ask-docs.md)** — operating the Ask Docs RAG module. Document management, LLM mode switching (Anthropic vs Ollama), reranker, reading the chat answers.
- **[admin-dashboard.md](./admin-dashboard.md)** — interpreting `/admin/modules/ask-docs`. Stat cards, token usage chart, mode breakdown, query log, drill-down.

## Lifecycle

- **[backup-restore.md](./backup-restore.md)** — when, how, recovering from disaster. The backup file IS A CREDENTIAL — read this twice.
- **[upgrade.md](./upgrade.md)** — pulling new portal versions, applying migrations, rolling back if needed.
- **[configuration.md](./configuration.md)** — every `.env` variable, what it does, when to change it. Includes `SECRET_KEY` rotation procedure.

## When things go wrong

- **[troubleshooting.md](./troubleshooting.md)** — symptoms-first index. First-boot failures, document indexing, chat errors, admin UI issues, backup/restore failures, healthcheck weirdness.

---

## Reading order recommendations

**First time installing:** install → first-run → security → backup-restore.

**Existing operator, new feature on the radar:** ask-docs → admin-dashboard. If you want to switch LLM modes: ask-docs → configuration → security.

**Got paged at 2am:** troubleshooting. Symptom-first.

**Planning a migration to new hardware:** backup-restore (cross-host restore section).

**Customer asking "is this safe to install?":** security. Send them sections 1–3 (threat model, what's protected, what you need to do).

---

## Doc structure conventions

- **All paths are relative** so these docs render correctly both as repo files AND if we ever embed them in the portal as a `/help` route
- **Code blocks include the directory context** (e.g., "From the repo root:") since many commands are sensitive to working directory
- **Warnings are flagged with ⚠️** for things that can lose data or leak secrets
- **Cross-references use full filenames** (`./install.md` not `install`) for portability
- **Versions are written as `0.5.0`** matching `backend/VERSION`
- **Customer-facing examples use `your-company.com`** — replace with the actual customer domain when applying

---

## Versioning + updates

These docs ship in the portal repo at `portal/docs/`. They're tied to the portal version — checkout the tag matching your install (e.g., `git checkout portal-v0.5.0`) to read the docs that match your code.

If you find a doc that's out of date relative to the running code, file a bug — docs that lie are worse than no docs.

---

## See also (outside this docs/ tree)

- **`portal/README.md`** — high-level "what works today" feature list with sub-plan history
- **`docs/superpowers/specs/*.md`** (in the parent `hoelscher-automation` repo) — design docs for each sub-plan; useful for "why was X built this way?" archaeology
- **`docs/superpowers/plans/*.md`** — task-by-task implementation plans; useful for understanding the rollout sequence

The `docs/superpowers/` tree is **internal documentation** — design intent, decision logs, implementation plans. The `portal/docs/` tree (where you are now) is **operator documentation** — how to install, configure, and operate the running system. Keep them separate; they have different audiences.

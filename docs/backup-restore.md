# Backup & Restore Runbook

When, how, and what to do when something goes wrong. Read this before you put real data in the portal.

The mechanics live in two host-side scripts at the repo root: `scripts/backup.sh` and `scripts/restore.sh`. Both must be run from the repo root.

---

## What's in a backup

A backup tar.gz contains everything needed to reconstruct an identical install on the same or a different host:

| File | Contents |
|---|---|
| `.env` | Your full env including `SECRET_KEY`, `POSTGRES_PASSWORD`, `ANTHROPIC_API_KEY`, etc. |
| `postgres.dump` | `pg_dump -Fc` of the entire portal database — users, queries, configs, modules, etc. |
| `qdrant_snapshot.snapshot` | Native Qdrant snapshot of the `ask_docs_chunks` collection (vector embeddings) |
| `uploads/` | Mirror of the `portal_uploads` Docker volume (raw uploaded files) |
| `MANIFEST.json` | sha256s of the four files above + portal version + timestamp + a credentials warning |

**Total size** scales with your corpus. Empty install: ~64 KB. With 100 indexed PDFs and 1000 chat queries: ~50 MB.

---

## ⚠️ The backup file IS A CREDENTIAL

Read this twice. The tar.gz has `mode 0600` (owner-readable only) when produced by `backup.sh`, but anyone who can `cp` it from your server now holds:

- `SECRET_KEY` — decrypts every encrypted secret in `module_configs` (Anthropic key today; Voyage / Hoelscher proxy keys in future)
- Your raw `ANTHROPIC_API_KEY` — your Anthropic billing
- `POSTGRES_PASSWORD` — full DB write access
- The Postgres dump — every user, every query, every module config
- The Qdrant snapshot — every embedded chunk of every uploaded document

**Treat backup files like password vault exports:**

- Encrypt at rest: `gpg --symmetric --cipher-algo AES256 portal-backup-*.tar.gz`
- Transmit over secure channels only (SSH/SCP, no email, no shared cloud drive without encryption)
- Limit who has access on the backup destination (chmod 700 the directory)
- Rotate them like any other backup — keep N most recent, delete older

---

## Taking a backup

### One-off

From the repo root:

```bash
bash scripts/backup.sh --output ~/portal-backups
```

Output:

```
▶ Portal backup starting (version=0.5.0, ts=2026-05-10T19-00-00Z)
▶ Copying .env
▶ Creating Qdrant snapshot
▶ Dumping Postgres (pg_dump -Fc)
▶ Copying uploads
▶ Building manifest
▶ Packaging to /home/you/portal-backups/portal-backup-2026-05-10T19-00-00Z.tar.gz
▶ Verifying archive integrity

✓ Backup complete
  path: /home/you/portal-backups/portal-backup-2026-05-10T19-00-00Z.tar.gz
  size: 64K  (mode 0600)
  sha256: a3e88417...

  ⚠ This archive contains .env (SECRET_KEY + credentials).
```

Save the sha256 somewhere — you can verify the archive hasn't been tampered with later by re-computing it.

### Automated (cron)

Add to root's crontab (`sudo crontab -e`):

```cron
# Daily backup at 03:00 local
0 3 * * * cd /home/you/portal && bash scripts/backup.sh --output /var/backups/portal/ 2>&1 | logger -t portal-backup
```

Then rotate them with logrotate or a tiny helper script:

```bash
# Keep last 14 days
find /var/backups/portal/ -name 'portal-backup-*.tar.gz' -mtime +14 -delete
```

### Off-host

The backup file is local to the host. To survive a host loss, you need to ship it offsite:

- **Restic / borg / kopia** to a cloud bucket — handles encryption + dedup + versioning
- **rsync over SSH** to a different machine on a regular schedule
- **rclone** to S3 / B2 / R2 with `--encrypt` if you don't already have backup-time encryption

Whatever you pick, **test the restore from the offsite copy at least once** before relying on it.

### Backup timing

Backups happen with all services running — no maintenance window. The portal is:

- **Read-consistent for Postgres** — `pg_dump` uses transactional snapshot isolation; the dump represents the DB at one point in time regardless of concurrent writes
- **Read-consistent for Qdrant** — the snapshot API freezes the collection at one point in time
- **Slightly inconsistent across the two** — a chat query that lands between the Qdrant snapshot (taken first) and the pg_dump (taken second) creates an `ask_docs_queries` row whose cited chunks ARE in the snapshot but the row itself is in the dump. Net effect: complete and correct. The reverse order would produce orphaned-query rows in the dump pointing at chunks not in the snapshot — worse. We deliberately do Qdrant first.
- **Possibly missing in-flight uploads** — a doc uploaded mid-backup might be in the `uploads/` mirror but not in the Postgres dump (or vice versa). Acceptable trade for not requiring a maintenance window. If you care, take backups during low-traffic windows.

---

## Restoring from a backup

### What restore does

1. Validates the manifest (refuses tampered files + newer-version backups)
2. Shows you the `.env` differences between host current and backup (key NAMES only — values masked)
3. Asks if you want to apply the backup's `.env` (default NO)
4. Asks you to type `WIPE` to confirm the destructive operation
5. Stops backend, worker, frontend (postgres + qdrant + ollama stay up)
6. (Optionally) replaces `.env`
7. `pg_restore --clean --if-exists` against the running Postgres (drops + recreates every table)
8. Uploads the Qdrant snapshot (overwrites the existing collection via `priority=snapshot`)
9. Wipes `/app/data/uploads` and copies the backup's uploads over
10. Restarts backend, worker, frontend
11. Waits up to 60 seconds for backend healthcheck

**Maintenance window:** typically 5–15 seconds end-to-end for a small install. Customer-facing chat returns connection errors during this window. Schedule it.

### Same-host restore (most common)

You're rolling back a botched config change or recovering from corruption on the same machine that took the backup. Your existing `.env` already has the right `SECRET_KEY`.

```bash
cd /path/to/portal
bash scripts/restore.sh ~/portal-backups/portal-backup-2026-05-10T19-00-00Z.tar.gz
```

You'll be asked twice:

1. **Apply the backup's `.env`?** — Press Enter to keep your current `.env` (recommended — same host, same `SECRET_KEY`, no need to swap)
2. **Type `WIPE` to proceed** — Type it exactly to confirm

Restore takes ~10 seconds. Output ends with:

```
✓ Restore complete (version 0.5.0)
  Verify at http://localhost:5173
```

### Cross-host restore (moving the install)

You're restoring on a fresh host. You need the backup's `.env` so `SECRET_KEY` matches the encrypted secrets in the dumped `module_configs`.

```bash
cd /path/to/portal-on-new-host
# Generate a stub .env first (just so the script's preflight passes)
cp .env.example .env
# Set just enough to make startup happy: a valid SECRET_KEY + POSTGRES_PASSWORD
# (these will be overwritten by the backup .env in step 7)
docker compose up -d
sleep 10
bash scripts/restore.sh ~/portal-backups/portal-backup-2026-05-10T19-00-00Z.tar.gz
```

When prompted "Apply the backup's `.env`?" — answer **y**. Your stub `.env` gets saved as `.env.pre-restore.<timestamp>` and the backup's `.env` becomes the active one.

After restore, verify chat works (it'll prove `SECRET_KEY` rotated correctly + the encrypted Anthropic key is now decryptable).

### Automated / unattended restore

For scripts (e.g., a "rebuild from latest backup" automation):

```bash
bash scripts/restore.sh /path/to/backup.tar.gz --yes
```

`--yes` skips both confirmation prompts. With `--yes`, the script will **never** apply the backup's `.env` automatically (too dangerous without operator review). If you need unattended cross-host restore, copy the `.env` separately:

```bash
tar xzf backup.tar.gz -C /tmp/extracted ./.env
cp /tmp/extracted/.env /path/to/portal/.env
docker compose up -d --force-recreate backend worker
bash scripts/restore.sh backup.tar.gz --yes
```

---

## Recovering from a failed restore

`restore.sh` exits non-zero on any failure. Common cases + recovery:

### Manifest validation failed

Output:

```
ERROR: Backup manifest validation failed (see traceback above).
  Common causes: wrong file, truncated archive, manifest tampered, backup from a newer portal version.
```

The script exits BEFORE any destructive operation, so your install is unchanged. Check:
- Is the file path correct?
- Is the archive intact? `tar tzf path/to/backup.tar.gz` should not error.
- Did someone modify the file between backup + restore? Re-check the sha256 you noted at backup time.
- Is the backup from a newer portal version than the current install? Restore refuses this — upgrade your install first.

### pg_restore failed mid-restore

If pg_restore crashes (DB connection lost, disk full mid-restore, etc.) but Qdrant snapshot already applied — the install is in a "split-brain" state with old vectors + partially-restored Postgres.

**Recovery: re-run the restore.**

```bash
bash scripts/restore.sh /path/to/backup.tar.gz --yes
```

Both `pg_restore --clean --if-exists` and the Qdrant snapshot upload (`priority=snapshot`) are idempotent — re-running fully overwrites whatever state was left behind. No special "rollback" command needed.

### Backend doesn't become healthy in 60s

```
⚠ Backend did not become healthy within 60s. Last 50 log lines:
<docker compose logs --tail=50 backend output>

  Re-run restore.sh with the same archive — both pg_restore and Qdrant snapshot upload are idempotent.
```

Read the logs. Common causes:
- `SECRET_KEY` mismatch between host `.env` and the encrypted secrets in the restored Postgres → backend crashes on first chat (decryption fails). Apply the backup's `.env` and re-run restore.
- Migration drift — if you restored a backup from an older portal version into a newer install, schema may need migration. `docker compose exec backend alembic upgrade head`.
- Real container crash — `docker compose ps backend`; restart manually if needed.

---

## Verification after restore

Always verify the restore produced a working install:

```bash
# 1. Backend health
curl -sf http://localhost:8000/api/health
# Should return: {"status":"ok"}

# 2. Login as admin (use credentials from before backup)
curl -s -c /tmp/c.txt -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@your-company.com&password=YOUR_PASSWORD"
# Should return: HTTP 204 (no body)

# 3. Dashboard counts match expectation
curl -s -b /tmp/c.txt http://localhost:8000/api/admin/modules/ask-docs/dashboard \
  | python3 -m json.tool | grep -E '"total"|"count"'
# Compare against pre-backup state if you noted it

# 4. Chat actually works (proves Qdrant + Anthropic + DB all wired)
curl -s -N -b /tmp/c.txt -X POST http://localhost:8000/api/modules/ask-docs/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "smoke test after restore"}'
# Should stream SSE events ending with "type": "final"

rm -f /tmp/c.txt
```

If all four checks pass, the restore is good. If any fail, check `docker compose logs backend` and re-run restore if needed.

---

## Disaster recovery scenarios

### "I lost the host"

You have a recent backup offsite. New host:

1. Provision the OS + Docker (per [install.md](./install.md))
2. `git clone` the portal repo
3. Skip the .env setup — restore will provide it
4. Cross-host restore (above)

End-to-end ~15 minutes for a vanilla rebuild.

### "Someone deleted all the documents"

Restore the last backup that has the documents.

If the restore would also wipe legitimate work that happened after the deletion:

1. Restore to a SECOND install (separate compose project, different ports — see [Operating multiple installs](#operating-multiple-installs) below)
2. Manually copy the documents you need back via the upload UI
3. Discard the second install

This is fiddly but the only way to merge state across two diverged points in time. The restore tool has no merge mode by design.

### "I rotated `SECRET_KEY` and forgot to clear `module_configs`"

Result: every chat fails with `DecryptionError`.

Fix:

```bash
docker compose exec -T postgres psql -U portal -d portal -c "DELETE FROM module_configs;"
docker compose up -d --force-recreate backend
# Then re-enter your Anthropic key via /admin/modules/ask-docs/config
```

This is documented in [configuration.md → Rotating SECRET_KEY](./configuration.md#rotating-secret_key) but worth repeating because it's a common pitfall.

---

## Operating multiple installs

Sometimes you want a second install on the same host (for staging, for testing a restore, for a customer demo). Compose supports this via the project name flag:

```bash
cd /path/to/portal
COMPOSE_PROJECT_NAME=portal-staging docker compose up -d
```

The new project gets its own:
- Container names (`portal-staging-backend-1`, etc.)
- Named volumes (`portal-staging_postgres_data`, etc.)
- Network namespace

You'll need a separate `.env` with non-colliding ports:

```
BACKEND_PORT=8001     # main install uses 8000
# Frontend port is also fixed at 5173 in compose; override there too
```

Backups + restores work the same — just point at the right project's containers (the script auto-detects via `docker compose ps`).

---

## See also

- [install.md](./install.md) — first-time install
- [configuration.md](./configuration.md) — `SECRET_KEY` lifecycle
- [troubleshooting.md](./troubleshooting.md) — diagnosis when restore fails

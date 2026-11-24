# Upgrade Guide

How to pull a new portal version into an existing install. Most upgrades are non-disruptive (a few seconds of backend restart). Schema changes need an Alembic migration.

---

## Before you upgrade

1. **Take a backup.** Always. See [backup-restore.md](./backup-restore.md). If the upgrade goes sideways, you can restore the pre-upgrade state.

2. **Check the release notes** for the version you're upgrading to. Look for:
   - Schema migrations (almost always — minor version bumps add features that need columns/tables)
   - Breaking config changes (rare; we try not to break `.env` between releases)
   - New required env vars
   - Deprecation warnings

3. **Check version compatibility for restore** — if you ever need to roll back, the older portal version refuses backups newer than itself. Forward-compat (older backup → newer install) usually works thanks to Alembic forward-migrations, but verify after.

---

## Standard upgrade

```bash
cd /path/to/portal

# 1. Backup first (non-negotiable for production)
bash scripts/backup.sh --output ~/portal-backups

# 2. Pull the latest release
git pull origin main

# 3. Pull updated Docker images (in case base images changed)
docker compose pull

# 4. Rebuild backend + worker + frontend images (deps or build steps may have changed)
docker compose build backend worker frontend

# 5. Apply any pending Alembic migrations
docker compose up -d postgres
sleep 3
docker compose run --rm backend alembic upgrade head

# 6. Recreate all services with the new image
docker compose up -d --force-recreate

# 7. Wait for healthy
sleep 15
docker compose ps
```

All services should be `(healthy)` within ~30 seconds. If something stays unhealthy, see [troubleshooting.md](./troubleshooting.md#first-boot-failures).

### Verify the upgrade

```bash
# Backend reports the new version
curl -sf http://localhost:8000/api/health
# → {"status": "ok"}

# Login + dashboard works
# (Browser test — log in to your portal as admin, click around)

# Chat still works
# (Ask a question against an indexed document)
```

If anything's broken: restore the pre-upgrade backup.

---

## `PORTAL_VERSION`

Nothing to edit (0.7.1+): the version is `backend/VERSION` in the release you pulled, read by the backend
and by `scripts/backup.sh` / `scripts/restore.sh`. Rebuild the backend after the pull so it reports it. An
older `.env` may still carry a `PORTAL_VERSION=` line; it is ignored, so delete it.

The version is what phone-home heartbeats report to the Operator Console and what backup manifests carry
(restore refuses a backup from a newer portal). To make the running backend report it after a pull:

```bash
docker compose up -d --build backend worker
```

---

## Common upgrade gotchas

### "alembic upgrade head" reports new migrations but applies none

Probably an `env.py` import path issue with a new model. Check the Alembic logs:

```bash
docker compose logs backend --tail=50 | grep alembic
```

Most often: a new model wasn't added to `app/models/__init__.py` or `alembic/env.py`. The migration file lists the change but Alembic can't see the model to autogen against.

### Backend crashes after upgrade with `pydantic.ValidationError`

A new env var was added to the config validator and your `.env` doesn't have it. Check the error message — it'll name the missing field. Add it to `.env`, recreate backend.

### Frontend shows blank page after upgrade

Vite's HMR cache may have stale references to deleted files. Force recreate frontend:

```bash
docker compose up -d --force-recreate frontend
```

If that doesn't fix it, hard-refresh the browser (Cmd-Shift-R / Ctrl-Shift-R) to bypass any cached JS bundles.

### "Module config secrets are unreadable" after upgrade

You probably DIDN'T change `SECRET_KEY` — but somehow the encrypted secrets in `module_configs` can't be decrypted. Possible causes:

1. The Fernet key derivation salt/info changed in the new release (we wouldn't do this without a migration script — file a bug if it happened)
2. Postgres data is from a backup made under a different `SECRET_KEY` than the current `.env`

Recovery:

```bash
# Drop the unreadable rows
docker compose exec -T postgres psql -U portal -d portal -c "DELETE FROM module_configs;"
docker compose up -d --force-recreate backend
# Re-enter Anthropic key via /admin/modules/ask-docs/config
```

---

## Rolling back

If the upgrade has issues you can't immediately fix, roll back to the pre-upgrade backup:

```bash
# 1. Roll the code back
git log --oneline -10                                    # find the previous release commit
git checkout <previous-release-commit>

# 2. Rebuild the OLD image
docker compose build backend worker

# 3. Restore the pre-upgrade backup
bash scripts/restore.sh ~/portal-backups/portal-backup-PRE_UPGRADE.tar.gz

# 4. Verify
docker compose ps
curl -sf http://localhost:8000/api/health
```

The restore handles everything (DB, Qdrant, uploads, optionally `.env`). After it completes, the install is back to the pre-upgrade state.

---

## Major version upgrades

Single-major-step upgrades (e.g., 0.5.x → 0.6.x) follow the standard procedure above.

Skipping major versions (e.g., 0.5.x → 0.7.x) is **not supported**. Migrations may not apply cleanly, and post-migration data fixups in 0.6.x may be required before 0.7.x can boot.

If you've been on an old version for a while, upgrade through each major version in sequence, taking a backup at each step.

### v0.6.x → v0.7.0 specifics

v0.7.0 switches the frontend from a Vite dev server to a compiled production build (smaller image, faster cold start, no source maps). The standard upgrade procedure works, but two things are worth knowing:

- **Frontend image must be rebuilt** — the new `frontend/Dockerfile` is multi-stage with a `runtime` target. `docker compose pull` won't help here (we don't publish images); `docker compose build frontend` runs the new build inside the multi-stage Dockerfile. The standard upgrade's `docker compose build backend worker` line should become `docker compose build backend worker frontend` for this upgrade.

- **For developers using `docker-compose.override.yml`**: the override now needs `build.target: dev` to opt into the dev image (see the updated `docker-compose.override.yml.example`). After updating your local override, you also need to renew the anonymous `node_modules` volume once: `docker compose up -d --force-recreate -V frontend`. Without `-V`, the stale volume from the v0.6.x dev image will mask the new dev image's pre-installed `node_modules` and you'll see `vite: not found`. Operators (no override) are unaffected by this dev-mode quirk.

---

## See also

- [install.md](./install.md) — first-time install
- [backup-restore.md](./backup-restore.md) — backup before upgrade, restore for rollback
- [configuration.md](./configuration.md) — env var changes between versions

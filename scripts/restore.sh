#!/usr/bin/env bash
# Portal restore — wipes current state + applies a backup tar.gz produced by backup.sh.
#
# DESTRUCTIVE: this drops all current data (Postgres tables, Qdrant collections,
# uploaded files). Use --yes to skip the confirmation prompt for automation.
#
# Maintenance window: backend, worker, and frontend are stopped during the
# restore (~5-15s for a small install). Customer-facing chat returns connection
# errors during this window — schedule accordingly.
#
# Recovery from partial failure: re-run restore.sh with the same archive.
# pg_restore --clean --if-exists is idempotent; Qdrant `priority=snapshot`
# upload fully overwrites the existing collection. The restore is therefore
# safe to retry as long as the archive is intact.
#
# Usage: bash scripts/restore.sh BACKUP.tar.gz [--yes]
#
# Run from the repo root.

set -euo pipefail
umask 077

if [[ $# -lt 1 ]]; then
    sed -n '2,18p' "$0"; exit 1
fi
ARCHIVE="$1"; shift
ASSUME_YES=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --yes) ASSUME_YES=1; shift ;;
        *) echo "Unknown arg: $1" >&2; exit 1 ;;
    esac
done

if [[ ! -f "$ARCHIVE" ]]; then
    echo "ERROR: $ARCHIVE not found" >&2; exit 1
fi
if [[ ! -f .env ]]; then
    echo "ERROR: .env not found in cwd. Run from the portal repo root." >&2; exit 1
fi
for var in POSTGRES_USER POSTGRES_DB; do
    grep -q "^${var}=" .env || { echo "ERROR: ${var} missing from .env" >&2; exit 1; }
done
for svc in postgres qdrant backend; do
    if ! docker compose ps "$svc" --format '{{.Status}}' | grep -q "Up"; then
        echo "ERROR: portal-$svc is not running. Start the stack first: docker compose up -d" >&2
        exit 1
    fi
done

# Cheap integrity preflight before we ask the operator to type WIPE
echo "▶ Verifying archive integrity"
tar tzf "$ARCHIVE" >/dev/null 2>&1 || {
    echo "ERROR: $ARCHIVE is not a valid tar.gz" >&2; exit 1
}

# ── Setup ────────────────────────────────────────────────────────────────────
WORK=$(mktemp -d "/tmp/portal-restore-XXXXXX")
BACKEND_CONTAINER=$(docker compose ps backend --format '{{.Name}}' | head -1)

# Cleanup: workdir + any orphaned snapshot/work-dir copies in the backend container
trap 'rm -rf "$WORK"; docker compose exec -T backend rm -rf /tmp/snap.snapshot /tmp/restore-work 2>/dev/null || true' EXIT

echo "▶ Extracting $ARCHIVE → $WORK"
# --no-same-owner: don't chown to the original UID (might not exist on this host)
# --no-overwrite-dir: don't replace dir attributes
# (modern GNU tar refuses absolute paths and `..` by default; this is belt+suspenders)
tar xzf "$ARCHIVE" -C "$WORK" --no-same-owner --no-overwrite-dir

# ── 1. Validate manifest ─────────────────────────────────────────────────────
CURRENT_VERSION=$(grep '^PORTAL_VERSION=' .env | cut -d= -f2- || echo "0.0.0")
CURRENT_VERSION=${CURRENT_VERSION:-0.0.0}

echo "▶ Validating manifest (current portal=$CURRENT_VERSION)"
docker compose exec -T backend rm -rf /tmp/restore-work
docker cp "$WORK/." "$BACKEND_CONTAINER:/tmp/restore-work/"
if ! docker compose exec -T backend python -m scripts.backup_manifest validate /tmp/restore-work \
        --current-portal-version "$CURRENT_VERSION"; then
    echo "" >&2
    echo "ERROR: Backup manifest validation failed (see traceback above)." >&2
    echo "  Common causes: wrong file, truncated archive, manifest tampered, backup from a newer portal version." >&2
    exit 1
fi
docker compose exec -T backend rm -rf /tmp/restore-work

BACKUP_VERSION=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['portal_version'])" "$WORK/MANIFEST.json")
echo "  backup version: $BACKUP_VERSION"

# ── 2. .env diff (key NAMES only — never print values) + apply prompt ───────
# Showing actual diff would leak SECRET_KEY/ANTHROPIC_API_KEY into terminal logs.
echo ""
echo "▶ .env keys that differ between host and backup (values masked):"
HOST_KEYS=$(grep -oE '^[A-Z_][A-Z0-9_]*=' .env | sort -u)
BACK_KEYS=$(grep -oE '^[A-Z_][A-Z0-9_]*=' "$WORK/.env" | sort -u)
HOST_KV=$(grep -E '^[A-Z_][A-Z0-9_]*=' .env       | sort -u | sha256sum | cut -d' ' -f1)
BACK_KV=$(grep -E '^[A-Z_][A-Z0-9_]*=' "$WORK/.env" | sort -u | sha256sum | cut -d' ' -f1)
diff <(echo "$HOST_KEYS") <(echo "$BACK_KEYS") || true
if [[ "$HOST_KV" == "$BACK_KV" ]]; then
    echo "  All keys + values are byte-identical (sha256: ${HOST_KV:0:12}…)"
else
    echo "  Some VALUES differ (sha256 host=${HOST_KV:0:12}… backup=${BACK_KV:0:12}…)"
fi
echo ""

APPLY_ENV=0
if [[ $ASSUME_YES -eq 1 ]]; then
    APPLY_ENV=0  # in --yes mode, never overwrite .env automatically
    echo "  (--yes: keeping host .env, NOT applying backup .env)"
else
    read -r -p "Apply the backup's .env over your current .env? [y/N] " ans
    if [[ "$ans" =~ ^[yY]$ ]]; then
        APPLY_ENV=1
    fi
fi

# ── 3. Confirm wipe ──────────────────────────────────────────────────────────
if [[ $ASSUME_YES -ne 1 ]]; then
    echo ""
    echo "▶ This will WIPE all current portal data:"
    echo "    - all Postgres tables (users, queries, configs, …)"
    echo "    - the ask_docs_chunks Qdrant collection"
    echo "    - all uploaded files"
    echo "  Backend, worker, and frontend will be stopped during the restore."
    read -r -p "Continue? Type 'WIPE' to proceed: " confirm
    if [[ "$confirm" != "WIPE" ]]; then
        echo "Aborted."
        exit 1
    fi
fi

# ── 4. Stop all write-side services (maintenance window starts) ─────────────
# Backend is stopped too — we use `docker compose run --rm` for the helpers
# below so chat requests can't see a half-restored DB / Qdrant.
echo "▶ Stopping backend, worker, frontend (entering maintenance window)"
docker compose stop backend worker frontend

# ── 5. Apply .env if requested ───────────────────────────────────────────────
if [[ $APPLY_ENV -eq 1 ]]; then
    echo "▶ Backing up current .env → .env.pre-restore.$(date -u +%s) and applying backup .env"
    cp .env ".env.pre-restore.$(date -u +%s)"
    cp "$WORK/.env" .env
fi

# ── 6. Restore Postgres ──────────────────────────────────────────────────────
echo "▶ Restoring Postgres"
PG_USER=$(grep '^POSTGRES_USER=' .env | cut -d= -f2-)
PG_DB=$(grep '^POSTGRES_DB=' .env | cut -d= -f2-)
docker compose exec -T postgres pg_restore --clean --if-exists -d "$PG_DB" -U "$PG_USER" < "$WORK/postgres.dump"

# ── 7. Restore Qdrant snapshot via transient backend container ─────────────
# `docker compose run --rm` creates a one-shot container with the same image
# + same network + same env vars. The -v mount lets the helper read the
# snapshot directly from the host work_dir without docker cp.
echo "▶ Restoring Qdrant snapshot"
docker compose run --rm -T -v "$WORK:/work" backend \
    python -m scripts.qdrant_snapshot restore /work/qdrant_snapshot.snapshot

# ── 8. Restore uploads via transient backend container ──────────────────────
# Mount the host work_dir AND let the transient container see the named
# `portal_uploads` volume by inheriting the backend service definition.
# NOTE: no `|| true` here — we want any failure (permission denied, disk full,
# missing source dir) to abort the restore loudly via `set -e` rather than
# silently report success with zero uploads restored.
echo "▶ Restoring uploads"
docker compose run --rm -T -v "$WORK:/work" backend \
    bash -c 'set -e; find /app/data/uploads -mindepth 1 -delete; if [ -d /work/uploads ]; then cp -r /work/uploads/. /app/data/uploads/; else echo "WARN: backup has no uploads dir" >&2; fi'

# ── 9. Restart write-side services (maintenance window ends) ────────────────
echo "▶ Starting backend, worker, frontend"
docker compose start backend worker frontend

# ── 10. Wait for backend healthy ─────────────────────────────────────────────
echo "▶ Waiting for backend to be healthy"
for i in {1..30}; do
    if curl -sf http://localhost:8000/api/health >/dev/null 2>&1; then
        echo ""
        echo "✓ Restore complete (version $BACKUP_VERSION)"
        echo "  Verify at http://localhost:5173"
        exit 0
    fi
    sleep 2
done

echo ""
echo "⚠ Backend did not become healthy within 60s. Last 50 log lines:" >&2
docker compose logs --tail=50 backend >&2 || true
echo "" >&2
echo "  Re-run restore.sh with the same archive — both pg_restore and Qdrant snapshot upload are idempotent." >&2
exit 1

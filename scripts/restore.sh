#!/usr/bin/env bash
# Portal restore — wipes current state + applies a backup tar.gz produced by backup.sh.
#
# DESTRUCTIVE: this drops all current data (Postgres tables, Qdrant collections,
# uploaded files). Use --yes to skip the confirmation prompt for automation.
#
# Usage: bash scripts/restore.sh BACKUP.tar.gz [--yes]
#
# Run from the repo root.

set -euo pipefail

if [[ $# -lt 1 ]]; then
    sed -n '2,11p' "$0"; exit 1
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
for svc in postgres qdrant backend; do
    if ! docker compose ps "$svc" --format '{{.Status}}' | grep -q "Up"; then
        echo "ERROR: portal-$svc is not running. Start the stack first: docker compose up -d" >&2
        exit 1
    fi
done

# ── Setup ────────────────────────────────────────────────────────────────────
WORK=$(mktemp -d "/tmp/portal-restore-XXXXXX")
trap "rm -rf $WORK" EXIT

echo "▶ Extracting $ARCHIVE → $WORK"
tar xzf "$ARCHIVE" -C "$WORK"

# ── 1. Validate manifest ─────────────────────────────────────────────────────
CURRENT_VERSION=$(grep '^PORTAL_VERSION=' .env | cut -d= -f2 || echo "0.0.0")
CURRENT_VERSION=${CURRENT_VERSION:-0.0.0}

echo "▶ Validating manifest (current portal=$CURRENT_VERSION)"
BACKEND_CONTAINER=$(docker compose ps backend --format '{{.Name}}' | head -1)
docker cp "$WORK/." "$BACKEND_CONTAINER:/tmp/restore-work/"
docker compose exec -T backend python -m scripts.backup_manifest validate /tmp/restore-work \
    --current-portal-version "$CURRENT_VERSION"
docker compose exec -T backend rm -rf /tmp/restore-work

BACKUP_VERSION=$(python3 -c "import json; print(json.load(open('$WORK/MANIFEST.json'))['portal_version'])")
echo "  backup version: $BACKUP_VERSION"

# ── 2. .env diff + apply prompt ──────────────────────────────────────────────
echo ""
echo "▶ .env diff (host current vs backup):"
diff -u .env "$WORK/.env" || true
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
    read -r -p "Continue? Type 'WIPE' to proceed: " confirm
    if [[ "$confirm" != "WIPE" ]]; then
        echo "Aborted."
        exit 1
    fi
fi

# ── 4. Stop the write-side services that don't need to be up for restore ───
# We keep `backend` UP because steps 7+8 use `docker compose exec backend`
# (Qdrant snapshot upload via the Python helper, uploads dir cleanup).
# `worker` is stopped so arq jobs can't pick up half-restored DB state.
# `frontend` is stopped so admins can't trigger writes mid-restore.
echo "▶ Stopping worker, frontend (backend stays up for restore helpers)"
docker compose stop worker frontend

# ── 5. Apply .env if requested ───────────────────────────────────────────────
if [[ $APPLY_ENV -eq 1 ]]; then
    echo "▶ Backing up current .env → .env.pre-restore.$(date -u +%s) and applying backup .env"
    cp .env ".env.pre-restore.$(date -u +%s)"
    cp "$WORK/.env" .env
fi

# ── 6. Restore Postgres ──────────────────────────────────────────────────────
echo "▶ Restoring Postgres"
PG_USER=$(grep '^POSTGRES_USER=' .env | cut -d= -f2)
PG_DB=$(grep '^POSTGRES_DB=' .env | cut -d= -f2)
docker compose exec -T postgres pg_restore --clean --if-exists -d "$PG_DB" -U "$PG_USER" < "$WORK/postgres.dump"

# ── 7. Restore Qdrant snapshot ───────────────────────────────────────────────
# The Python helper reads the snapshot file from inside the BACKEND container's
# filesystem, then PUTs the bytes to Qdrant via HTTP. So we copy the snapshot
# into the backend container, not the qdrant container.
echo "▶ Restoring Qdrant snapshot"
docker cp "$WORK/qdrant_snapshot.snapshot" "$BACKEND_CONTAINER:/tmp/snap.snapshot"
docker compose exec -T backend python -m scripts.qdrant_snapshot restore /tmp/snap.snapshot
docker compose exec -T backend rm -f /tmp/snap.snapshot

# ── 8. Restore uploads ───────────────────────────────────────────────────────
echo "▶ Restoring uploads"
docker compose exec -T backend find /app/data/uploads -mindepth 1 -delete
docker cp "$WORK/uploads/." "$BACKEND_CONTAINER:/app/data/uploads/"

# ── 9. Restart write-side services ───────────────────────────────────────────
# Backend wasn't stopped, but restart it so the SECRET_KEY change (if any)
# from step 5 takes effect — pydantic-settings caches at import time.
echo "▶ Restarting backend (for env reload), starting worker + frontend"
docker compose restart backend
docker compose start worker frontend

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
echo "⚠ Backend did not become healthy within 60s. Check 'docker compose logs backend'."
exit 1

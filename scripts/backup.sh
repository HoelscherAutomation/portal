#!/usr/bin/env bash
# Portal backup — produces a tar.gz of the entire portal install state.
#
# Includes: .env (with SECRET_KEY!), Postgres dump, Qdrant snapshot, uploads volume.
# The output file IS A CREDENTIAL — store encrypted at rest.
#
# Usage: bash scripts/backup.sh [--output DIR]
#   --output DIR   write tar.gz here (default: ./)
#
# Run from the repo root.

set -euo pipefail

OUTPUT_DIR="."
while [[ $# -gt 0 ]]; do
    case "$1" in
        --output) OUTPUT_DIR="$2"; shift 2 ;;
        -h|--help) sed -n '2,15p' "$0"; exit 0 ;;
        *) echo "Unknown arg: $1" >&2; exit 1 ;;
    esac
done

mkdir -p "$OUTPUT_DIR"
OUTPUT_DIR=$(cd "$OUTPUT_DIR" && pwd)  # absolute

# ── Preflight ────────────────────────────────────────────────────────────────
if [[ ! -f .env ]]; then
    echo "ERROR: .env not found in cwd. Run from the portal repo root." >&2
    exit 1
fi
for svc in backend postgres qdrant; do
    if ! docker compose ps "$svc" --format '{{.Status}}' | grep -q "Up"; then
        echo "ERROR: portal-$svc is not running. Start the stack first: docker compose up -d" >&2
        exit 1
    fi
done

# ── Setup ────────────────────────────────────────────────────────────────────
TS=$(date -u +%Y-%m-%dT%H-%M-%SZ)
WORK=$(mktemp -d "/tmp/portal-backup-$TS-XXXXXX")
trap "rm -rf $WORK" EXIT

PORTAL_VERSION=$(grep '^PORTAL_VERSION=' .env | cut -d= -f2 || echo "0.0.0")
PORTAL_VERSION=${PORTAL_VERSION:-0.0.0}

echo "▶ Portal backup starting (version=$PORTAL_VERSION, ts=$TS)"
echo "  work dir: $WORK"

# ── 1. .env ──────────────────────────────────────────────────────────────────
echo "▶ Copying .env"
cp .env "$WORK/.env"

# ── 2. Postgres dump ─────────────────────────────────────────────────────────
echo "▶ Dumping Postgres (pg_dump -Fc)"
PG_USER=$(grep '^POSTGRES_USER=' .env | cut -d= -f2)
PG_DB=$(grep '^POSTGRES_DB=' .env | cut -d= -f2)
docker compose exec -T postgres pg_dump -Fc -U "$PG_USER" "$PG_DB" > "$WORK/postgres.dump"

# ── 3. Qdrant snapshot ───────────────────────────────────────────────────────
echo "▶ Creating Qdrant snapshot"
SNAP_INFO=$(docker compose exec -T backend python -m scripts.qdrant_snapshot create)
SNAP_NAME="${SNAP_INFO%%:*}"
SNAP_PATH="${SNAP_INFO#*:}"
echo "  snapshot: $SNAP_NAME at $SNAP_PATH"

QDRANT_CONTAINER=$(docker compose ps qdrant --format '{{.Name}}' | head -1)
docker cp "$QDRANT_CONTAINER:$SNAP_PATH" "$WORK/qdrant_snapshot.snapshot"

# ── 4. Uploads volume ────────────────────────────────────────────────────────
echo "▶ Copying uploads"
mkdir -p "$WORK/uploads"
BACKEND_CONTAINER=$(docker compose ps backend --format '{{.Name}}' | head -1)
# docker cp requires the source dir to exist; backend always creates /app/data/uploads
docker cp "$BACKEND_CONTAINER:/app/data/uploads/." "$WORK/uploads/"

# ── 5. Manifest ──────────────────────────────────────────────────────────────
# The Python helper runs INSIDE the backend container, so we copy the work dir
# in, build the manifest there, and copy MANIFEST.json back out.
echo "▶ Building manifest"
docker cp "$WORK/." "$BACKEND_CONTAINER:/tmp/manifest-work/"
docker compose exec -T backend python -m scripts.backup_manifest build /tmp/manifest-work \
    --portal-version "$PORTAL_VERSION" \
    --source-hostname "$(hostname)"
docker cp "$BACKEND_CONTAINER:/tmp/manifest-work/MANIFEST.json" "$WORK/MANIFEST.json"
docker compose exec -T backend rm -rf /tmp/manifest-work

# ── 6. Tar it up ─────────────────────────────────────────────────────────────
ARCHIVE="$OUTPUT_DIR/portal-backup-$TS.tar.gz"
echo "▶ Packaging to $ARCHIVE"
tar czf "$ARCHIVE" -C "$WORK" .

SIZE=$(du -h "$ARCHIVE" | cut -f1)
SHA=$(sha256sum "$ARCHIVE" | cut -d' ' -f1)

echo ""
echo "✓ Backup complete"
echo "  path: $ARCHIVE"
echo "  size: $SIZE"
echo "  sha256: $SHA"
echo ""
echo "  ⚠ This archive contains .env (SECRET_KEY + credentials)."
echo "  ⚠ Treat it as a secret — encrypt at rest, transmit over secure channels."

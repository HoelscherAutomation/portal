"""Backup manifest builder + validator.

build_manifest(work_dir, portal_version, source_hostname) walks the staged
backup directory and produces a dict suitable for json.dump → MANIFEST.json.

validate_manifest(work_dir, current_portal_version) reads MANIFEST.json,
re-checks every sha256, and refuses to proceed if (a) a checksum no longer
matches or (b) the backup was taken from a portal newer than the current.
"""
import argparse
import hashlib
import json
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_BUF = 1024 * 1024  # 1MB read chunks


class ManifestValidationError(Exception):
    """Raised when a manifest doesn't match the on-disk archive contents."""


def sha256_of_path(path: Path) -> str:
    """sha256 of a file, or of a directory's recursive sorted contents (file paths + bytes)."""
    h = hashlib.sha256()
    if path.is_file():
        with path.open("rb") as f:
            while chunk := f.read(_BUF):
                h.update(chunk)
        return h.hexdigest()
    if path.is_dir():
        for child in sorted(path.rglob("*")):
            if not child.is_file():
                continue
            # Mix the relative path into the hash so file moves change the digest
            h.update(str(child.relative_to(path)).encode("utf-8"))
            h.update(b"\0")
            with child.open("rb") as f:
                while chunk := f.read(_BUF):
                    h.update(chunk)
        return h.hexdigest()
    raise FileNotFoundError(path)


def _dir_size_and_count(path: Path) -> tuple[int, int]:
    total = 0
    count = 0
    for child in path.rglob("*"):
        if child.is_file():
            total += child.stat().st_size
            count += 1
    return total, count


def build_manifest(
    work_dir: Path,
    *,
    portal_version: str,
    source_hostname: str | None = None,
) -> dict[str, Any]:
    """Walk work_dir's components and produce a manifest dict."""
    env_path = work_dir / ".env"
    pg_path = work_dir / "postgres.dump"
    qd_path = work_dir / "qdrant_snapshot.snapshot"
    uploads_path = work_dir / "uploads"
    upload_total, upload_count = _dir_size_and_count(uploads_path) if uploads_path.exists() else (0, 0)

    return {
        "portal_version": portal_version,
        "backup_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_hostname": source_hostname or socket.gethostname(),
        "components": {
            "env": {
                "sha256": sha256_of_path(env_path),
                "size_bytes": env_path.stat().st_size,
            },
            "postgres": {
                "sha256": sha256_of_path(pg_path),
                "size_bytes": pg_path.stat().st_size,
            },
            "qdrant": {
                "sha256": sha256_of_path(qd_path),
                "size_bytes": qd_path.stat().st_size,
            },
            "uploads": {
                "sha256_top_level": sha256_of_path(uploads_path),
                "file_count": upload_count,
                "total_size_bytes": upload_total,
            },
        },
        "warnings": [
            "Backup includes .env containing SECRET_KEY and other credentials. "
            "Treat the tar.gz as a credential — store encrypted at rest.",
        ],
    }


def _parse_version(s: str) -> tuple[int, ...]:
    """Tolerant semver-ish: '0.6.0' → (0, 6, 0). Bad parses → (0, 0, 0)."""
    out = []
    for part in s.split("."):
        try:
            out.append(int(part.split("-")[0].split("+")[0]))
        except ValueError:
            out.append(0)
    return tuple(out)


def validate_manifest(work_dir: Path, *, current_portal_version: str) -> None:
    """Verify MANIFEST.json shape, version compat, and all sha256s. Raises on any mismatch."""
    manifest_path = work_dir / "MANIFEST.json"
    if not manifest_path.is_file():
        raise ManifestValidationError(f"MANIFEST.json missing in {work_dir}")
    manifest = json.loads(manifest_path.read_text())

    if "portal_version" not in manifest:
        raise ManifestValidationError(
            "MANIFEST.json missing required key 'portal_version'. "
            "Refusing — manifest may be tampered or from an incompatible backup tool."
        )
    backup_v = _parse_version(manifest["portal_version"])
    current_v = _parse_version(current_portal_version)
    if backup_v > current_v:
        raise ManifestValidationError(
            f"Backup portal version ({manifest['portal_version']}) is newer than current "
            f"({current_portal_version}); refusing to apply."
        )

    components = manifest.get("components", {})
    paths = {
        "env": work_dir / ".env",
        "postgres": work_dir / "postgres.dump",
        "qdrant": work_dir / "qdrant_snapshot.snapshot",
    }
    for key, path in paths.items():
        expected = components.get(key, {}).get("sha256")
        actual = sha256_of_path(path)
        if expected != actual:
            raise ManifestValidationError(
                f"Component {key} sha256 mismatch: manifest={expected} actual={actual}"
            )
    # Uploads dir uses sha256_top_level
    expected = components.get("uploads", {}).get("sha256_top_level")
    actual = sha256_of_path(work_dir / "uploads")
    if expected != actual:
        raise ManifestValidationError(
            f"Component uploads sha256_top_level mismatch: manifest={expected} actual={actual}"
        )


def _main() -> int:
    parser = argparse.ArgumentParser(description="Backup manifest builder/validator")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_build = sub.add_parser("build")
    p_build.add_argument("work_dir")
    p_build.add_argument("--portal-version", required=True)
    p_build.add_argument("--source-hostname", default=None)
    p_build.add_argument("--out", default=None, help="Manifest output path (default: work_dir/MANIFEST.json)")

    p_validate = sub.add_parser("validate")
    p_validate.add_argument("work_dir")
    p_validate.add_argument("--current-portal-version", required=True)

    args = parser.parse_args()
    work_dir = Path(args.work_dir)

    if args.cmd == "build":
        manifest = build_manifest(
            work_dir,
            portal_version=args.portal_version,
            source_hostname=args.source_hostname,
        )
        out = Path(args.out) if args.out else work_dir / "MANIFEST.json"
        out.write_text(json.dumps(manifest, indent=2))
        print(f"Wrote {out}")
        return 0

    if args.cmd == "validate":
        validate_manifest(work_dir, current_portal_version=args.current_portal_version)
        print(f"Manifest valid: {work_dir / 'MANIFEST.json'}")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(_main())

"""Tests for the backup manifest builder/validator."""
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.backup_manifest import (
    ManifestValidationError,
    build_manifest,
    sha256_of_path,
    validate_manifest,
)


def test_sha256_of_file(tmp_path: Path):
    f = tmp_path / "x.txt"
    f.write_bytes(b"hello world")
    # sha256("hello world") = b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9
    assert sha256_of_path(f) == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"


def test_sha256_of_directory_is_stable(tmp_path: Path):
    """Directory hash should be deterministic across calls (sorted-iterate inside)."""
    (tmp_path / "a.txt").write_bytes(b"a")
    (tmp_path / "b.txt").write_bytes(b"b")
    h1 = sha256_of_path(tmp_path)
    h2 = sha256_of_path(tmp_path)
    assert h1 == h2
    # Adding a file changes the hash
    (tmp_path / "c.txt").write_bytes(b"c")
    assert sha256_of_path(tmp_path) != h1


def test_build_manifest_includes_all_components(tmp_path: Path):
    """Build a minimal work_dir with the expected component files + verify shape."""
    (tmp_path / ".env").write_bytes(b"SECRET_KEY=test\n")
    (tmp_path / "postgres.dump").write_bytes(b"fake pg dump")
    (tmp_path / "qdrant_snapshot.snapshot").write_bytes(b"fake snap")
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "file1.pdf").write_bytes(b"pdf")

    manifest = build_manifest(tmp_path, portal_version="0.6.0", source_hostname="testhost")

    assert manifest["portal_version"] == "0.6.0"
    assert manifest["source_hostname"] == "testhost"
    assert "backup_at_utc" in manifest
    assert set(manifest["components"].keys()) == {"env", "postgres", "qdrant", "uploads"}
    assert manifest["components"]["env"]["sha256"] == sha256_of_path(tmp_path / ".env")
    assert manifest["components"]["postgres"]["size_bytes"] == len(b"fake pg dump")
    assert manifest["components"]["uploads"]["file_count"] == 1
    assert "warnings" in manifest
    assert any("credential" in w.lower() or ".env" in w.lower() for w in manifest["warnings"])


def test_validate_manifest_passes_for_intact_archive(tmp_path: Path):
    (tmp_path / ".env").write_bytes(b"SECRET_KEY=x\n")
    (tmp_path / "postgres.dump").write_bytes(b"d")
    (tmp_path / "qdrant_snapshot.snapshot").write_bytes(b"s")
    (tmp_path / "uploads").mkdir()
    manifest = build_manifest(tmp_path, portal_version="0.5.0", source_hostname="h")
    (tmp_path / "MANIFEST.json").write_text(json.dumps(manifest))
    # Should not raise
    validate_manifest(tmp_path, current_portal_version="0.6.0")


def test_validate_manifest_rejects_tampered_file(tmp_path: Path):
    (tmp_path / ".env").write_bytes(b"original\n")
    (tmp_path / "postgres.dump").write_bytes(b"d")
    (tmp_path / "qdrant_snapshot.snapshot").write_bytes(b"s")
    (tmp_path / "uploads").mkdir()
    manifest = build_manifest(tmp_path, portal_version="0.5.0", source_hostname="h")
    (tmp_path / "MANIFEST.json").write_text(json.dumps(manifest))

    # Tamper with the .env after manifest was built
    (tmp_path / ".env").write_bytes(b"tampered\n")

    with pytest.raises(ManifestValidationError, match="env.*sha256"):
        validate_manifest(tmp_path, current_portal_version="0.6.0")


def test_validate_manifest_rejects_newer_portal_version(tmp_path: Path):
    (tmp_path / ".env").write_bytes(b"x\n")
    (tmp_path / "postgres.dump").write_bytes(b"d")
    (tmp_path / "qdrant_snapshot.snapshot").write_bytes(b"s")
    (tmp_path / "uploads").mkdir()
    manifest = build_manifest(tmp_path, portal_version="2.0.0", source_hostname="h")
    (tmp_path / "MANIFEST.json").write_text(json.dumps(manifest))
    with pytest.raises(ManifestValidationError, match="newer"):
        validate_manifest(tmp_path, current_portal_version="0.6.0")

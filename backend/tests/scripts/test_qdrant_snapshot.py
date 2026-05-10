"""Tests for the Qdrant snapshot CLI helper."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scripts.qdrant_snapshot import (
    SnapshotError,
    create_snapshot,
    restore_snapshot,
)


async def test_create_snapshot_returns_name_and_path():
    """POST /collections/{name}/snapshots → returns the new snapshot name."""
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {"result": {"name": "snap-2026-05-10-180000.snapshot"}}

    with patch("scripts.qdrant_snapshot.httpx.AsyncClient") as fake_client_cls:
        fake_client = AsyncMock()
        fake_client.post.return_value = fake_response
        fake_client_cls.return_value.__aenter__.return_value = fake_client

        out = await create_snapshot(qdrant_url="http://qdrant:6333", collection="ask_docs_chunks")

    assert out["name"] == "snap-2026-05-10-180000.snapshot"
    # Container path is deterministic from collection + name
    assert out["container_path"] == "/qdrant/snapshots/ask_docs_chunks/snap-2026-05-10-180000.snapshot"
    fake_client.post.assert_awaited_once()
    assert fake_client.post.await_args.args[0].endswith("/collections/ask_docs_chunks/snapshots")


async def test_create_snapshot_raises_on_non_200():
    fake_response = MagicMock()
    fake_response.status_code = 500
    fake_response.text = "internal error"

    with patch("scripts.qdrant_snapshot.httpx.AsyncClient") as fake_client_cls:
        fake_client = AsyncMock()
        fake_client.post.return_value = fake_response
        fake_client_cls.return_value.__aenter__.return_value = fake_client

        with pytest.raises(SnapshotError, match="500"):
            await create_snapshot(qdrant_url="http://qdrant:6333", collection="ask_docs_chunks")


async def test_restore_snapshot_uploads_file():
    """restore_snapshot reads a local file + uploads to Qdrant via the recover endpoint."""
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {"result": True}

    with patch("scripts.qdrant_snapshot.httpx.AsyncClient") as fake_client_cls, \
         patch("scripts.qdrant_snapshot.Path") as fake_path_cls:
        fake_client = AsyncMock()
        fake_client.post.return_value = fake_response
        fake_client_cls.return_value.__aenter__.return_value = fake_client
        # Path("/tmp/snap").open("rb") → context manager yielding fake fh (streaming)
        fake_file = MagicMock()
        fake_fh = MagicMock()
        fake_file.open.return_value.__enter__.return_value = fake_fh
        fake_file.name = "snap.snapshot"
        fake_path_cls.return_value = fake_file

        await restore_snapshot(
            qdrant_url="http://qdrant:6333",
            collection="ask_docs_chunks",
            snapshot_path="/tmp/snap.snapshot",
        )

    fake_client.post.assert_awaited_once()
    url = fake_client.post.await_args.args[0]
    assert "/collections/ask_docs_chunks/snapshots/upload" in url


async def test_restore_snapshot_raises_on_non_200():
    fake_response = MagicMock()
    fake_response.status_code = 422
    fake_response.text = "snapshot format invalid"

    with patch("scripts.qdrant_snapshot.httpx.AsyncClient") as fake_client_cls, \
         patch("scripts.qdrant_snapshot.Path") as fake_path_cls:
        fake_client = AsyncMock()
        fake_client.post.return_value = fake_response
        fake_client_cls.return_value.__aenter__.return_value = fake_client
        fake_file = MagicMock()
        fake_fh = MagicMock()
        fake_file.open.return_value.__enter__.return_value = fake_fh
        fake_file.name = "snap.snapshot"
        fake_path_cls.return_value = fake_file

        with pytest.raises(SnapshotError, match="422"):
            await restore_snapshot(
                qdrant_url="http://qdrant:6333",
                collection="ask_docs_chunks",
                snapshot_path="/tmp/snap.snapshot",
            )

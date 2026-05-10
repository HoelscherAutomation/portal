"""Qdrant snapshot create/restore CLI.

Usage (inside the backend container):
    python -m scripts.qdrant_snapshot create [--collection ask_docs_chunks]
    python -m scripts.qdrant_snapshot restore <snapshot-path> [--collection ask_docs_chunks]

`create` POSTs to Qdrant's snapshot endpoint and prints `<name>:<container_path>` to
stdout — bash callers parse this to know which file to docker-cp out.

`restore` reads a snapshot file from disk and uploads it via the recover endpoint.
"""
import argparse
import asyncio
import sys
from pathlib import Path

import httpx

from app.config import get_settings


class SnapshotError(Exception):
    """Raised when Qdrant returns a non-2xx response."""


async def create_snapshot(*, qdrant_url: str, collection: str) -> dict:
    """POST /collections/{collection}/snapshots → returns {name, container_path}."""
    url = f"{qdrant_url.rstrip('/')}/collections/{collection}/snapshots"
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(url)
        if response.status_code != 200:
            raise SnapshotError(
                f"Qdrant returned {response.status_code} on snapshot create: {response.text[:200]}"
            )
        name = response.json()["result"]["name"]
    return {
        "name": name,
        "container_path": f"/qdrant/snapshots/{collection}/{name}",
    }


async def restore_snapshot(
    *,
    qdrant_url: str,
    collection: str,
    snapshot_path: str,
) -> None:
    """Upload a local snapshot file to Qdrant's recover endpoint."""
    path = Path(snapshot_path)
    data = path.read_bytes()
    url = f"{qdrant_url.rstrip('/')}/collections/{collection}/snapshots/upload?priority=snapshot"
    async with httpx.AsyncClient(timeout=600.0) as client:
        response = await client.put(
            url,
            files={"snapshot": (path.name, data, "application/octet-stream")},
        )
        if response.status_code != 200:
            raise SnapshotError(
                f"Qdrant returned {response.status_code} on snapshot upload: {response.text[:200]}"
            )


def _main() -> int:
    parser = argparse.ArgumentParser(description="Qdrant snapshot create/restore")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_create = sub.add_parser("create")
    p_create.add_argument("--collection", default="ask_docs_chunks")

    p_restore = sub.add_parser("restore")
    p_restore.add_argument("snapshot_path")
    p_restore.add_argument("--collection", default="ask_docs_chunks")

    args = parser.parse_args()
    qdrant_url = get_settings().qdrant_url

    if args.cmd == "create":
        result = asyncio.run(create_snapshot(qdrant_url=qdrant_url, collection=args.collection))
        # bash parses: name:container_path
        print(f"{result['name']}:{result['container_path']}")
        return 0

    if args.cmd == "restore":
        asyncio.run(restore_snapshot(
            qdrant_url=qdrant_url,
            collection=args.collection,
            snapshot_path=args.snapshot_path,
        ))
        print(f"Restored {args.snapshot_path} into collection {args.collection}")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(_main())

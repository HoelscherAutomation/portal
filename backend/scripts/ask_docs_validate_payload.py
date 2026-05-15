"""Validate that all Ask Docs Qdrant payloads have P2.1A metadata.

Run via:
    docker compose exec backend python -m scripts.ask_docs_validate_payload [--ignore-orphans]

Exit code 0 on full pass. Exit code 1 if any required field is missing on any
point, or any doc_id has no matching Postgres row (unless --ignore-orphans).
"""
import argparse
import asyncio
import logging
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_async_session
from app.modules.ask_docs.models import AskDocsDocument
from app.modules.ask_docs.vectorstore import VectorStore

logger = logging.getLogger("ask_docs.validate_payload")

_COLLECTION = "ask_docs_chunks"


async def run_validation(
    *,
    session: AsyncSession,
    vectorstore: VectorStore,
    ignore_orphans: bool = False,
    batch_size: int = 1024,
) -> dict[str, int]:
    """Scan every point and report violations. Returns counters + exit_code."""
    counters: dict[str, int] = {
        "scanned": 0,
        "missing_schema_version": 0,
        "missing_filename": 0,
        "missing_content_type": 0,
        "missing_uploaded_at": 0,
        "orphan_doc_ids": 0,
        "exit_code": 0,
    }
    client = vectorstore._get_client()
    # Read collection from the supplied vectorstore so tests can target their own
    # isolated collection while production runs against _COLLECTION.
    collection = vectorstore._collection
    offset = None
    seen_doc_ids: set[str] = set()

    while True:
        points, next_offset = await client.scroll(
            collection_name=collection, offset=offset, limit=batch_size, with_payload=True,
        )
        for point in points:
            counters["scanned"] += 1
            payload = point.payload or {}
            if payload.get("payload_schema_version") != 2:
                counters["missing_schema_version"] += 1
            for field in ("filename", "content_type", "uploaded_at"):
                if field not in payload:
                    counters[f"missing_{field}"] += 1
            doc_id = payload.get("doc_id")
            if doc_id:
                seen_doc_ids.add(doc_id)
        if next_offset is None:
            break
        offset = next_offset

    if seen_doc_ids:
        result = await session.execute(
            select(AskDocsDocument.id).where(AskDocsDocument.id.in_(seen_doc_ids))
        )
        live_doc_ids = {str(r) for r in result.scalars().all()}
        counters["orphan_doc_ids"] = len(seen_doc_ids - live_doc_ids)

    field_failed = any(counters[k] > 0 for k in (
        "missing_schema_version", "missing_filename", "missing_content_type", "missing_uploaded_at",
    ))
    orphan_failed = counters["orphan_doc_ids"] > 0 and not ignore_orphans
    if counters["orphan_doc_ids"] > 0 and ignore_orphans:
        logger.warning("WARNING: %d orphan doc_ids ignored", counters["orphan_doc_ids"])

    counters["exit_code"] = 1 if (field_failed or orphan_failed) else 0
    return counters


def _print_report(counters: dict[str, int]) -> None:
    print("Ask Docs payload validation")
    print("---------------------------")
    print(f"Total points scanned:        {counters['scanned']}")
    print(f"Missing schema_version:      {counters['missing_schema_version']}")
    print(f"Missing filename:            {counters['missing_filename']}")
    print(f"Missing content_type:        {counters['missing_content_type']}")
    print(f"Missing uploaded_at:         {counters['missing_uploaded_at']}")
    print(f"Orphan doc_ids:              {counters['orphan_doc_ids']}")
    print()
    print("PASS" if counters["exit_code"] == 0 else "FAIL")


async def _main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--ignore-orphans", action="store_true")
    args = parser.parse_args()

    s = get_settings()
    vectorstore = VectorStore(url=s.qdrant_url, collection_name=_COLLECTION, vector_size=768)
    async for session in get_async_session():
        try:
            counters = await run_validation(
                session=session, vectorstore=vectorstore, ignore_orphans=args.ignore_orphans,
            )
            _print_report(counters)
            return counters["exit_code"]
        finally:
            await vectorstore.aclose()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))

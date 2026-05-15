"""Delete Qdrant chunks whose doc_id has no matching Postgres row.

Run via:
    docker compose exec backend python -m scripts.ask_docs_delete_orphans [--yes]

Default mode is dry-run: lists orphan doc_ids without deleting. Pass --yes to
actually delete (or answer 'y' at the prompt).
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

logger = logging.getLogger("ask_docs.delete_orphans")

_COLLECTION = "ask_docs_chunks"


async def find_and_delete_orphans(
    *,
    session: AsyncSession,
    vectorstore: VectorStore,
    confirm: bool = False,
    batch_size: int = 1024,
) -> dict:
    """Find orphan doc_ids. If confirm=True, delete their chunks. Returns report.

    Returns: {orphan_doc_ids: list[str], deleted_doc_ids: list[str], dry_run: bool}
    """
    client = vectorstore._get_client()
    # Read collection from the supplied vectorstore so tests can target their own
    # isolated collection while production runs against _COLLECTION.
    collection = vectorstore._collection
    seen_doc_ids: set[str] = set()
    offset = None

    while True:
        points, next_offset = await client.scroll(
            collection_name=collection, offset=offset, limit=batch_size, with_payload=True,
        )
        for point in points:
            payload = point.payload or {}
            doc_id = payload.get("doc_id")
            if doc_id:
                seen_doc_ids.add(doc_id)
        if next_offset is None:
            break
        offset = next_offset

    if not seen_doc_ids:
        return {"orphan_doc_ids": [], "deleted_doc_ids": [], "dry_run": not confirm}

    result = await session.execute(
        select(AskDocsDocument.id).where(AskDocsDocument.id.in_(seen_doc_ids))
    )
    live_doc_ids = {str(r) for r in result.scalars().all()}
    orphans = sorted(seen_doc_ids - live_doc_ids)

    if not confirm:
        return {"orphan_doc_ids": orphans, "deleted_doc_ids": [], "dry_run": True}

    for doc_id in orphans:
        await vectorstore.delete_by_doc_id(doc_id)
        logger.info("Deleted orphan chunks for doc_id=%s", doc_id)

    return {"orphan_doc_ids": orphans, "deleted_doc_ids": orphans, "dry_run": False}


async def _main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--yes", action="store_true", help="Skip the prompt and delete immediately")
    args = parser.parse_args()

    s = get_settings()
    vectorstore = VectorStore(url=s.qdrant_url, collection_name=_COLLECTION, vector_size=768)
    async for session in get_async_session():
        try:
            preview = await find_and_delete_orphans(
                session=session, vectorstore=vectorstore, confirm=False,
            )
            if not preview["orphan_doc_ids"]:
                print("No orphans found.")
                return 0
            print(f"Found {len(preview['orphan_doc_ids'])} orphan doc_ids:")
            for d in preview["orphan_doc_ids"]:
                print(f"  - {d}")
            if not args.yes:
                resp = input("Delete these orphan chunks? [y/N] ").strip().lower()
                if resp != "y":
                    print("Aborted.")
                    return 0
            await find_and_delete_orphans(
                session=session, vectorstore=vectorstore, confirm=True,
            )
            return 0
        finally:
            await vectorstore.aclose()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))

"""Backfill Ask Docs Qdrant payloads with P2.1A metadata fields.

Run via:
    docker compose exec backend python -m scripts.ask_docs_backfill_payload

Idempotent: re-running is a no-op for chunks already at payload_schema_version == 2.
Resumable: persists scroll offset to ask_docs_migration_state so an interrupted run continues.
Observable: logs counters for scanned/updated/skipped/failed at exit.
"""
import asyncio
import logging
import sys
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_async_session
from app.modules.ask_docs.models import AskDocsDocument, AskDocsMigrationState
from app.modules.ask_docs.vectorstore import VectorStore

logger = logging.getLogger("ask_docs.backfill_payload")

_STATE_NAME = "backfill_payload_v2"
_COLLECTION = "ask_docs_chunks"


async def _load_state(session: AsyncSession) -> dict[str, Any]:
    row = await session.get(AskDocsMigrationState, _STATE_NAME)
    return dict(row.state) if row else {"offset": None}


async def _save_state(session: AsyncSession, state: dict[str, Any]) -> None:
    # NOTE: AskDocsMigrationState.updated_at has onupdate=func.now() declared as a
    # SQLAlchemy ORM hook, but the Core-level pg_insert + on_conflict_do_update
    # path bypasses ORM hooks. Set updated_at explicitly in the set_ dict.
    stmt = pg_insert(AskDocsMigrationState).values(name=_STATE_NAME, state=state)
    stmt = stmt.on_conflict_do_update(
        index_elements=["name"],
        set_={"state": state, "updated_at": func.now()},
    )
    await session.execute(stmt)
    await session.commit()


async def _clear_state(session: AsyncSession) -> None:
    row = await session.get(AskDocsMigrationState, _STATE_NAME)
    if row:
        await session.delete(row)
        await session.commit()


async def run_backfill(
    *,
    session: AsyncSession,
    vectorstore: VectorStore,
    batch_size: int = 256,
    max_batches: int | None = None,
) -> dict[str, int]:
    """Scroll all points; for each pre-v2 point, fetch the doc row and set new payload fields.

    Returns counter dict. max_batches is a test hook to simulate interruption.
    """
    counters: dict[str, int] = {
        "scanned": 0, "updated": 0,
        "skipped_already_v2": 0, "skipped_missing_doc": 0, "failed": 0,
    }
    state = await _load_state(session)
    offset = state.get("offset")
    batches_run = 0
    client = vectorstore._get_client()
    # Read collection from the supplied vectorstore so tests can target their
    # own isolated collection without forking the script.
    collection = vectorstore._collection

    while True:
        points, next_offset = await client.scroll(
            collection_name=collection,
            offset=offset,
            limit=batch_size,
            with_payload=True,
        )
        for point in points:
            counters["scanned"] += 1
            payload = point.payload or {}
            if payload.get("payload_schema_version") == 2:
                counters["skipped_already_v2"] += 1
                continue
            doc_id = payload.get("doc_id")
            if not doc_id:
                counters["failed"] += 1
                logger.warning("Point %s has no doc_id; skipping", point.id)
                continue
            doc_row = (await session.execute(
                select(AskDocsDocument).where(AskDocsDocument.id == doc_id)
            )).scalar_one_or_none()
            if doc_row is None:
                counters["skipped_missing_doc"] += 1
                logger.warning("Orphan chunk: point %s references missing doc %s", point.id, doc_id)
                continue
            try:
                await client.set_payload(
                    collection_name=collection,
                    payload={
                        "filename": doc_row.filename,
                        "content_type": doc_row.content_type,
                        "uploaded_by": doc_row.uploaded_by,
                        "uploaded_at": doc_row.uploaded_at.isoformat() + "Z",
                        "payload_schema_version": 2,
                    },
                    points=[point.id],
                )
                counters["updated"] += 1
            except Exception as exc:
                counters["failed"] += 1
                logger.exception(
                    "set_payload failed for point %s (doc_id=%s): %s",
                    point.id, doc_id, exc,
                )

        logger.info(
            "Batch %d complete — scanned=%d updated=%d skipped_already_v2=%d skipped_missing_doc=%d failed=%d",
            batches_run + 1,
            counters["scanned"], counters["updated"],
            counters["skipped_already_v2"], counters["skipped_missing_doc"], counters["failed"],
        )
        batches_run += 1
        if next_offset is None:
            break
        # Qdrant scroll offset for UUID-id collections is a UUID; str() round-trips
        # correctly through both JSONB storage and the qdrant_client scroll API.
        offset = next_offset
        await _save_state(session, {"offset": str(offset)})
        if max_batches is not None and batches_run >= max_batches:
            logger.info("max_batches reached; persisting state and stopping")
            return counters

    await _clear_state(session)
    logger.info("Backfill complete: %s", counters)
    return counters


async def _main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    s = get_settings()
    vectorstore = VectorStore(url=s.qdrant_url, collection_name=_COLLECTION, vector_size=768)
    async for session in get_async_session():
        try:
            try:
                counters = await run_backfill(session=session, vectorstore=vectorstore)
                logger.info("Backfill summary: %s", counters)
                return 0
            except Exception as exc:
                logger.exception("Backfill aborted: %s", exc)
                return 1
        finally:
            await vectorstore.aclose()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(_main()))
    except KeyboardInterrupt:
        sys.exit(130)

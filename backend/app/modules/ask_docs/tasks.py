"""arq tasks for Ask Docs document indexing."""
import logging
import uuid
from pathlib import Path

import app.database as db_module
from app.config import get_settings
from app.modules.ask_docs.chunker import chunk_pages
from app.modules.ask_docs.embeddings import EmbeddingsClient
from app.modules.ask_docs.models import AskDocsDocument, AskDocsStatus
from app.modules.ask_docs.parsers import ParserError, parse_to_pages
from app.modules.ask_docs.vectorstore import VectorStore
from app.secret_scrub import scrub_secrets

logger = logging.getLogger(__name__)

_COLLECTION_NAME = "ask_docs_chunks"


def _make_embeddings_client():
    """Factory — overridable in tests."""
    s = get_settings()
    return EmbeddingsClient(url=s.ollama_url, model=s.ask_docs_embedding_model)


def _make_vectorstore():
    """Factory — overridable in tests."""
    s = get_settings()
    return VectorStore(url=s.qdrant_url, collection_name=_COLLECTION_NAME, vector_size=768)


async def index_document(ctx: dict, document_id: str) -> None:
    """Parse → chunk → embed → store. Updates document.status throughout."""
    doc_uuid = uuid.UUID(document_id)
    settings = get_settings()

    async with db_module.async_session_maker() as session:
        doc = await session.get(AskDocsDocument, doc_uuid)
        if doc is None:
            logger.warning("index_document: doc %s not found", document_id)
            return
        doc.status = AskDocsStatus.indexing
        await session.commit()
        path = Path(doc.storage_path)
        content_type = doc.content_type
        filename = doc.filename

    error_msg: str | None = None
    chunk_count = 0
    try:
        pages = parse_to_pages(path, content_type)
        chunks = chunk_pages(
            pages,
            chunk_size_tokens=settings.ask_docs_chunk_size_tokens,
            overlap_tokens=settings.ask_docs_chunk_overlap_tokens,
        )

        embeddings_client = _make_embeddings_client()
        vectorstore = _make_vectorstore()
        try:
            await vectorstore.ensure_collection()
            vectors = await embeddings_client.embed_batch([c.text for c in chunks])
            points = [
                {
                    "vector": vec,
                    "payload": {
                        "doc_id": document_id,
                        "page_num": chunk.page_num,
                        "chunk_index": chunk.chunk_index,
                        "content": chunk.text,
                        "source_path": filename,
                    },
                }
                for chunk, vec in zip(chunks, vectors, strict=True)
            ]
            await vectorstore.upsert(points)
            chunk_count = len(points)
        finally:
            await embeddings_client.aclose()
            await vectorstore.aclose()

    except ParserError as exc:
        # Parser errors don't include credentials; raw scrub still cheap.
        error_msg = scrub_secrets(f"Parse error: {exc}")
        logger.warning("Parse failed for doc %s: %s", document_id, exc)
    except Exception as exc:
        # httpx / Ollama / Qdrant transport errors can embed full URLs
        # (and any auth params therein). Scrub before persisting to
        # error_message — admin dashboard surfaces this verbatim.
        error_msg = scrub_secrets(f"{type(exc).__name__}: {exc}")
        logger.exception("Indexing failed for doc %s", document_id)

    async with db_module.async_session_maker() as session:
        doc = await session.get(AskDocsDocument, doc_uuid)
        if doc is None:
            return
        if error_msg is None:
            doc.status = AskDocsStatus.indexed
            doc.chunk_count = chunk_count
            doc.error_message = None
        else:
            doc.status = AskDocsStatus.failed
            doc.error_message = error_msg
        await session.commit()

    logger.info(
        "index_document done: id=%s status=%s chunks=%d",
        document_id,
        AskDocsStatus.indexed if error_msg is None else AskDocsStatus.failed,
        chunk_count,
    )


async def delete_document_vectors(ctx: dict, document_id: str) -> None:
    """Remove a document's chunks from Qdrant."""
    vectorstore = _make_vectorstore()
    try:
        await vectorstore.delete_by_doc_id(document_id)
    finally:
        await vectorstore.aclose()
    logger.info("delete_document_vectors done: id=%s", document_id)

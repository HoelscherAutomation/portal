"""HTTP routes for Ask Docs document management."""
import json
import logging
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

from arq.connections import RedisSettings, create_pool
from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.backend import current_active_user
from app.config import get_settings
from app.database import get_async_session
from app.models import AskDocsDocument, User
from app.modules._config_service import load_config
from app.modules.ask_docs.chat import ChatOrchestrator
from app.modules.ask_docs.embeddings import EmbeddingsClient
from app.modules.ask_docs.llm_factory import make_llm_client
from app.modules.ask_docs.models import AskDocsStatus
from app.modules.ask_docs.reranker import Reranker
from app.modules.ask_docs.schemas import ChatRequest, DocumentRead
from app.modules.ask_docs.vectorstore import VectorStore

logger = logging.getLogger(__name__)

router = APIRouter()

# Module-level Reranker singleton — survives across chat requests so the ~80MB
# fastembed model loads ONCE per backend process, not once per request. Without
# this, every chat with rerank enabled would pay the 5-10s model load latency.
_reranker_singleton: Reranker | None = None


def _get_reranker() -> Reranker:
    """Return the per-process Reranker singleton, constructing on first call.

    The Reranker constructor itself is cheap (no model load) — the model loads
    lazily on the first .rerank() call against this instance. Once loaded, the
    encoder lives in memory for the rest of the process lifetime.
    """
    global _reranker_singleton
    if _reranker_singleton is None:
        _reranker_singleton = Reranker()
    return _reranker_singleton

_ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/markdown",
}


def _ask_docs_dir() -> Path:
    s = get_settings()
    path = Path(s.uploads_path) / "ask-docs"
    path.mkdir(parents=True, exist_ok=True)
    return path


async def _enqueue_index(doc_id: str) -> None:
    """Enqueue an index_document arq job. Overridable in tests."""
    from urllib.parse import urlparse
    settings = get_settings()
    url = urlparse(settings.redis_url)
    redis = await create_pool(RedisSettings(
        host=url.hostname or "redis",
        port=url.port or 6379,
        database=int(url.path.lstrip("/") or "0"),
    ))
    try:
        await redis.enqueue_job("index_document", doc_id)
    finally:
        await redis.close()


async def _enqueue_delete(doc_id: str) -> None:
    """Enqueue a delete_document_vectors arq job. Overridable in tests."""
    from urllib.parse import urlparse
    settings = get_settings()
    url = urlparse(settings.redis_url)
    redis = await create_pool(RedisSettings(
        host=url.hostname or "redis",
        port=url.port or 6379,
        database=int(url.path.lstrip("/") or "0"),
    ))
    try:
        await redis.enqueue_job("delete_document_vectors", doc_id)
    finally:
        await redis.close()


@router.post("/documents", response_model=DocumentRead, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    file: UploadFile,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> AskDocsDocument:
    if file.content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported content type: {file.content_type}",
        )

    content = await file.read()
    doc_id = uuid.uuid4()
    storage_path = _ask_docs_dir() / f"{doc_id}-{file.filename}"
    storage_path.write_bytes(content)

    document = AskDocsDocument(
        id=doc_id,
        filename=file.filename or "untitled",
        content_type=file.content_type,
        size_bytes=len(content),
        uploaded_by=user.id,
        status=AskDocsStatus.pending,
        chunk_count=0,
        storage_path=str(storage_path),
    )
    session.add(document)
    await session.commit()
    await session.refresh(document)

    try:
        await _enqueue_index(str(doc_id))
    except Exception:
        logger.exception("Failed to enqueue index_document for %s", doc_id)

    return document


@router.get("/documents", response_model=list[DocumentRead])
async def list_documents(
    _user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> list[AskDocsDocument]:
    rows = (
        await session.execute(
            select(AskDocsDocument).order_by(AskDocsDocument.uploaded_at.desc())
        )
    ).scalars().all()
    return list(rows)


@router.get("/documents/{document_id}", response_model=DocumentRead)
async def get_document(
    document_id: uuid.UUID,
    _user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> AskDocsDocument:
    doc = await session.get(AskDocsDocument, document_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return doc


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    _user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> Response:
    doc = await session.get(AskDocsDocument, document_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    storage_path = Path(doc.storage_path) if doc.storage_path else None
    await session.delete(doc)
    await session.commit()

    if storage_path and storage_path.exists():
        try:
            storage_path.unlink()
        except OSError as exc:
            logger.warning("Failed to remove %s: %s", storage_path, exc)
    try:
        await _enqueue_delete(str(document_id))
    except Exception:
        logger.exception("Failed to enqueue delete_document_vectors for %s", document_id)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _make_embeddings_client():
    s = get_settings()
    return EmbeddingsClient(url=s.ollama_url, model=s.ask_docs_embedding_model)


def _make_vectorstore():
    s = get_settings()
    return VectorStore(url=s.qdrant_url, collection_name="ask_docs_chunks", vector_size=768)


async def _make_orchestrator():
    """Build the chat orchestrator using the customer's saved LLM config."""
    s = get_settings()
    llm, mode = await make_llm_client()
    config = await load_config("ask-docs")
    reranker_enabled = config.get("reranker", {}).get("enabled", False)
    # Use the module-level singleton — model loads ONCE per process on first
    # actual rerank call, not once per chat request.
    reranker = _get_reranker() if reranker_enabled else None
    return ChatOrchestrator(
        embeddings=_make_embeddings_client(),
        vectorstore=_make_vectorstore(),
        llm=llm,
        llm_mode=mode,
        top_k=s.ask_docs_top_k,
        max_answer_tokens=s.ask_docs_max_answer_tokens,
        reranker=reranker,
        reranker_enabled=reranker_enabled,
    )


def _sanitize_error(exc: Exception) -> str:
    """Surface a short user-facing message for SSE error events."""
    msg = str(exc) or exc.__class__.__name__
    return msg[:500]


@router.post("/chat")
async def chat(
    payload: ChatRequest,
    user: User = Depends(current_active_user),
):
    if not payload.query.strip():
        raise HTTPException(status_code=400, detail="Query must not be empty")

    orchestrator = await _make_orchestrator()

    async def _event_stream() -> AsyncIterator[bytes]:
        try:
            async for event in orchestrator.run(query=payload.query, user_id=user.id):
                yield f"data: {json.dumps(event)}\n\n".encode("utf-8")
        except Exception as exc:
            # Headers already sent; can't return 5xx. Emit an error event so the
            # frontend can show the failure instead of seeing a silently truncated stream.
            logger.exception("Chat orchestration failed mid-stream")
            error_event = {"type": "error", "detail": _sanitize_error(exc)}
            yield f"data: {json.dumps(error_event)}\n\n".encode("utf-8")
        finally:
            await orchestrator.close_clients()

    return StreamingResponse(_event_stream(), media_type="text/event-stream")


@router.get("/chunks/{doc_id}/{chunk_index}")
async def get_chunk(
    doc_id: str,
    chunk_index: int,
    _user: User = Depends(current_active_user),
):
    """Fetch one chunk's payload by doc_id + chunk_index. Used by source preview."""
    vectorstore = _make_vectorstore()
    try:
        payload = await vectorstore.search_by_doc_chunk(doc_id=doc_id, chunk_index=chunk_index)
    finally:
        await vectorstore.aclose()
    if payload is None:
        raise HTTPException(status_code=404, detail="Chunk not found")
    return payload

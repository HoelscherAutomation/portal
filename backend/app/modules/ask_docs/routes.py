"""HTTP routes for Ask Docs document management."""
import logging
import uuid
from pathlib import Path

from arq.connections import RedisSettings, create_pool
from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.backend import current_active_user
from app.config import get_settings
from app.database import get_async_session
from app.models import AskDocsDocument, User
from app.modules.ask_docs.models import AskDocsStatus
from app.modules.ask_docs.schemas import DocumentRead

logger = logging.getLogger(__name__)

router = APIRouter()

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

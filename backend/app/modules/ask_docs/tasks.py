"""arq tasks for Ask Docs. Stubs in P1.1 Task 6 — real impl in Task 11."""
import logging

logger = logging.getLogger(__name__)


async def index_document(ctx: dict, document_id: str) -> None:
    """Stub. Real impl in Task 11."""
    logger.info("STUB index_document called for %s — real impl in P1.1 Task 11", document_id)


async def delete_document_vectors(ctx: dict, document_id: str) -> None:
    """Stub. Real impl in Task 11."""
    logger.info("STUB delete_document_vectors called for %s", document_id)

"""arq worker configuration. The worker container runs:

    arq app.workers.worker.WorkerSettings

Tasks live in their respective module packages (e.g. app.modules.ask_docs.tasks).
"""
import logging

from arq.connections import RedisSettings

from app.config import get_settings
from app.modules.ask_docs.tasks import delete_document_vectors, index_document

logger = logging.getLogger(__name__)


async def startup(ctx: dict) -> None:
    logger.info("arq worker starting up")


async def shutdown(ctx: dict) -> None:
    logger.info("arq worker shutting down")


def _redis_settings() -> RedisSettings:
    """Parse the REDIS_URL into arq RedisSettings."""
    from urllib.parse import urlparse

    url = urlparse(get_settings().redis_url)
    return RedisSettings(
        host=url.hostname or "redis",
        port=url.port or 6379,
        database=int(url.path.lstrip("/") or "0"),
    )


class WorkerSettings:
    redis_settings = _redis_settings()
    functions = [index_document, delete_document_vectors]
    on_startup = startup
    on_shutdown = shutdown
    job_timeout = 60 * 30  # 30 minutes for large doc indexing
    max_jobs = 4

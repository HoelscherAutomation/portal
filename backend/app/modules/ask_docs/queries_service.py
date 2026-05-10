"""Query log service for the admin dashboard.

list_queries: paginated newest-first, joined with users for email.
get_query_detail: single query + sources_used (already stored on the row by chat orchestrator).
"""
from typing import Any

from sqlalchemy import desc, select

import app.database as db_module
from app.models import AskDocsQuery, User


class QueryNotFound(Exception):
    """Raised by get_query_detail when no row matches the id."""


def _row_to_dict(row: AskDocsQuery, email: str | None) -> dict[str, Any]:
    return {
        "id": row.id,
        "user_email": email,
        "query_text": row.query_text,
        "answer_text": row.answer_text,
        "citation_count": row.citation_count,
        "llm_mode": row.llm_mode,
        "tokens_used": row.tokens_used,
        "duration_ms": row.duration_ms,
        "sources_used": row.sources_used or [],
        "created_at": row.created_at.isoformat(),
    }


async def list_queries(*, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    """Newest queries first, paginated. Joins users for email, NULL for deleted users."""
    async with db_module.async_session_maker() as session:
        result = await session.execute(
            select(AskDocsQuery, User.email)
            .outerjoin(User, AskDocsQuery.user_id == User.id)
            .order_by(desc(AskDocsQuery.created_at))
            .limit(limit)
            .offset(offset)
        )
        return [_row_to_dict(q, email) for q, email in result.all()]


async def get_query_detail(query_id: int) -> dict[str, Any]:
    """Full row including sources_used. Raises QueryNotFound if missing."""
    async with db_module.async_session_maker() as session:
        result = await session.execute(
            select(AskDocsQuery, User.email)
            .outerjoin(User, AskDocsQuery.user_id == User.id)
            .where(AskDocsQuery.id == query_id)
        )
        row = result.one_or_none()
        if row is None:
            raise QueryNotFound(query_id)
        q, email = row
        return _row_to_dict(q, email)

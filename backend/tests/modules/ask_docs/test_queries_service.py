import pytest
from sqlalchemy import select

import app.database as db_module
from app.models import AskDocsQuery, User
from app.modules.ask_docs.queries_service import (
    QueryNotFound,
    get_query_detail,
    list_queries,
)
from tests.test_auth import _create_user


async def _get_user_by_email(email: str) -> User:
    async with db_module.async_session_maker() as session:
        result = await session.execute(select(User).where(User.email == email))
        return result.scalar_one()


async def _add_query(*, user_id=None, query_text="q", sources=None):
    async with db_module.async_session_maker() as session:
        q = AskDocsQuery(
            user_id=user_id,
            query_text=query_text,
            answer_text="answer body",
            citation_count=len(sources or []),
            llm_mode="anthropic",
            tokens_used=100,
            duration_ms=1000,
            sources_used=sources or [],
        )
        session.add(q)
        await session.commit()
        await session.refresh(q)
        return q.id


async def test_list_returns_empty_when_no_rows():
    rows = await list_queries(limit=10, offset=0)
    assert rows == []


async def test_list_includes_user_email():
    await _create_user("dashuser@example.com", "test-password-123")
    user = await _get_user_by_email("dashuser@example.com")
    qid = await _add_query(user_id=user.id, query_text="hello")
    rows = await list_queries(limit=10, offset=0)
    assert len(rows) == 1
    assert rows[0]["id"] == qid
    assert rows[0]["user_email"] == "dashuser@example.com"
    assert rows[0]["query_text"] == "hello"


async def test_list_handles_null_user():
    """user_id is FK ON DELETE SET NULL — list should still return the row."""
    await _add_query(user_id=None)
    rows = await list_queries(limit=10, offset=0)
    assert rows[0]["user_email"] is None


async def test_list_paginates_newest_first():
    for i in range(5):
        await _add_query(query_text=f"q{i}")
    page1 = await list_queries(limit=2, offset=0)
    page2 = await list_queries(limit=2, offset=2)
    assert len(page1) == 2 and len(page2) == 2
    assert page1[0]["query_text"] == "q4"  # most recent first
    assert page2[0]["query_text"] == "q2"


async def test_detail_returns_full_row_with_sources():
    sources = [
        {"number": 1, "filename": "a.pdf", "page_num": 5, "content": "chunk A"},
        {"number": 2, "filename": "b.pdf", "page_num": 1, "content": "chunk B"},
    ]
    qid = await _add_query(sources=sources, query_text="what is X?")
    detail = await get_query_detail(qid)
    assert detail["id"] == qid
    assert detail["query_text"] == "what is X?"
    assert detail["answer_text"] == "answer body"
    assert detail["sources_used"] == sources


async def test_detail_404_when_missing():
    with pytest.raises(QueryNotFound):
        await get_query_detail(999999)

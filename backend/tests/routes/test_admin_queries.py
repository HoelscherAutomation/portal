import pytest
from httpx import AsyncClient

import app.database as db_module
from app.models import AskDocsQuery
from tests.test_auth import _create_user


async def _login(client: AsyncClient, *, superuser=True):
    email = "admin@example.com" if superuser else "user@example.com"
    await _create_user(email, "test-password-123", superuser=superuser)
    r = await client.post("/api/auth/login", data={"username": email, "password": "test-password-123"})
    assert r.status_code in (200, 204)


async def _add_query(*, user_id=None, sources=None):
    async with db_module.async_session_maker() as session:
        q = AskDocsQuery(
            user_id=user_id,
            query_text="test q",
            answer_text="test a [1]",
            citation_count=1,
            llm_mode="anthropic",
            tokens_used=200,
            duration_ms=1500,
            sources_used=sources or [],
        )
        session.add(q)
        await session.commit()
        await session.refresh(q)
        return q.id


async def test_list_requires_superuser(client: AsyncClient):
    r = await client.get("/api/admin/modules/ask-docs/queries")
    assert r.status_code == 401
    await _login(client, superuser=False)
    r = await client.get("/api/admin/modules/ask-docs/queries")
    assert r.status_code == 403


async def test_list_returns_rows_with_user_email(client: AsyncClient):
    await _login(client)
    qid = await _add_query()
    r = await client.get("/api/admin/modules/ask-docs/queries?limit=10&offset=0")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) >= 1
    assert "user_email" in rows[0]
    assert "query_text" in rows[0]


async def test_list_pagination(client: AsyncClient):
    await _login(client)
    for _ in range(3):
        await _add_query()
    r1 = await client.get("/api/admin/modules/ask-docs/queries?limit=2&offset=0")
    r2 = await client.get("/api/admin/modules/ask-docs/queries?limit=2&offset=2")
    assert len(r1.json()) == 2
    assert len(r2.json()) >= 1


async def test_detail_404_missing(client: AsyncClient):
    await _login(client)
    r = await client.get("/api/admin/modules/ask-docs/queries/999999")
    assert r.status_code == 404


async def test_detail_returns_sources_used(client: AsyncClient):
    await _login(client)
    sources = [{"number": 1, "filename": "h.pdf", "page_num": 2, "content": "chunk text"}]
    qid = await _add_query(sources=sources)
    r = await client.get(f"/api/admin/modules/ask-docs/queries/{qid}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == qid
    assert body["sources_used"] == sources

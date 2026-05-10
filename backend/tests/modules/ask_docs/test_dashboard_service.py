import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import text

import app.database as db_module
from app.models import AskDocsDocument, AskDocsQuery
from app.modules._config_service import save_config
from app.modules.ask_docs.dashboard_service import compute_dashboard
from app.modules.ask_docs.models import AskDocsStatus


async def _add_doc(filename="x.pdf", status=AskDocsStatus.indexed, chunk_count=10):
    async with db_module.async_session_maker() as session:
        doc = AskDocsDocument(
            id=uuid.uuid4(), filename=filename, content_type="application/pdf",
            size_bytes=100, status=status, chunk_count=chunk_count,
            storage_path=f"/tmp/{filename}",
        )
        session.add(doc)
        await session.commit()


async def _add_query(*, mode="anthropic", tokens=100, duration_ms=1500, days_ago=0):
    async with db_module.async_session_maker() as session:
        q = AskDocsQuery(
            query_text="q", answer_text="a", citation_count=0, llm_mode=mode,
            tokens_used=tokens, duration_ms=duration_ms,
        )
        session.add(q)
        await session.flush()
        if days_ago:
            await session.execute(
                text("UPDATE ask_docs_queries SET created_at = now() - (:d || ' days')::interval WHERE id = :id"),
                {"d": str(days_ago), "id": q.id},
            )
        await session.commit()


async def test_zero_state():
    out = await compute_dashboard()
    assert out["documents"]["total"] == 0
    assert out["documents"]["by_status"] == {"pending": 0, "indexing": 0, "indexed": 0, "failed": 0}
    assert out["documents"]["total_chunks"] == 0
    assert out["queries_30d"]["count"] == 0
    assert out["queries_30d"]["tokens"] == 0
    assert out["queries_30d"]["cost_usd_estimated"] == 0.0
    assert out["queries_30d"]["by_mode"] == []
    assert len(out["queries_30d"]["tokens_per_day"]) == 30
    assert all(d["tokens"] == 0 for d in out["queries_30d"]["tokens_per_day"])
    assert out["queries_30d"]["avg_latency_ms"] is None
    assert out["queries_30d"]["p95_latency_ms"] is None
    assert out["update_banner"] is None


async def test_doc_breakdown_counts_status():
    await _add_doc(status=AskDocsStatus.indexed, chunk_count=5)
    await _add_doc(status=AskDocsStatus.indexed, chunk_count=3)
    await _add_doc(status=AskDocsStatus.failed, chunk_count=0)
    await _add_doc(status=AskDocsStatus.pending, chunk_count=0)
    out = await compute_dashboard()
    assert out["documents"]["total"] == 4
    assert out["documents"]["by_status"]["indexed"] == 2
    assert out["documents"]["by_status"]["failed"] == 1
    assert out["documents"]["by_status"]["pending"] == 1
    assert out["documents"]["total_chunks"] == 8


async def test_30d_aggregates():
    await _add_query(mode="anthropic", tokens=1000, duration_ms=2000)
    await _add_query(mode="anthropic", tokens=2000, duration_ms=4000)
    await _add_query(mode="ollama", tokens=500, duration_ms=1000)
    out = await compute_dashboard()
    assert out["queries_30d"]["count"] == 3
    assert out["queries_30d"]["tokens"] == 3500
    assert out["queries_30d"]["avg_latency_ms"] == pytest.approx(2333, abs=1)
    by_mode = {row["mode"]: row for row in out["queries_30d"]["by_mode"]}
    assert by_mode["anthropic"]["count"] == 2
    assert by_mode["anthropic"]["tokens"] == 3000
    assert by_mode["ollama"]["count"] == 1
    assert by_mode["ollama"]["tokens"] == 500


async def test_30d_window_excludes_old_rows():
    await _add_query(tokens=999, days_ago=45)  # outside window
    await _add_query(tokens=1, days_ago=0)
    out = await compute_dashboard()
    assert out["queries_30d"]["count"] == 1
    assert out["queries_30d"]["tokens"] == 1


async def test_tokens_per_day_has_30_entries_oldest_first():
    await _add_query(tokens=100, days_ago=5)
    out = await compute_dashboard()
    series = out["queries_30d"]["tokens_per_day"]
    assert len(series) == 30
    # First entry is the oldest (29 days ago); last is today
    assert series[0]["date"] < series[-1]["date"]
    # The day 5 ago should have 100 tokens
    sums = {d["date"]: d["tokens"] for d in series}
    target_date = (datetime.utcnow() - timedelta(days=5)).date().isoformat()
    assert sums[target_date] == 100


async def test_cost_uses_configured_mode_pricing():
    # Save anthropic config so dashboard knows which model to price against
    await save_config("ask-docs", {
        "llm_mode": "anthropic",
        "anthropic": {"api_key": "sk-test", "model": "claude-sonnet-4-6", "max_tokens": 1024},
        "ollama": {"url": "", "model": "", "max_tokens": 1024},
        "hoelscher_proxy": {},
    }, updated_by=None)
    await _add_query(mode="anthropic", tokens=1_000_000)
    out = await compute_dashboard()
    # 1M tokens at sonnet-4-6 ($6/M) = $6.00
    assert out["queries_30d"]["cost_usd_estimated"] == 6.0

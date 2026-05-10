"""Dashboard payload computation. Single function returns everything the
admin dashboard page needs in one round-trip."""
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select, text

import app.database as db_module
from app.models import AskDocsDocument, AskDocsQuery
from app.modules._config_service import load_config
from app.modules.ask_docs.models import AskDocsStatus
from app.modules.ask_docs.pricing import estimate_cost_usd

_ALL_STATUSES = ("pending", "indexing", "indexed", "failed")


async def compute_dashboard() -> dict[str, Any]:
    """Aggregate queries against ask_docs_documents + ask_docs_queries tables."""
    async with db_module.async_session_maker() as session:
        docs = await _doc_breakdown(session)
        q30d = await _query_30d_stats(session)

    # Cost estimate uses the currently-configured mode's model.
    config = await load_config("ask-docs")
    mode = config.get("llm_mode", "anthropic")
    model = config.get(mode, {}).get("model")
    q30d["cost_usd_estimated"] = estimate_cost_usd(mode, model, q30d["tokens"])

    return {
        "documents": docs,
        "queries_30d": q30d,
        "update_banner": None,  # MVP placeholder; future OC integration fills this
    }


async def _doc_breakdown(session) -> dict[str, Any]:
    rows = (await session.execute(
        select(AskDocsDocument.status, func.count(AskDocsDocument.id))
        .group_by(AskDocsDocument.status)
    )).all()
    by_status = {s: 0 for s in _ALL_STATUSES}
    for status, count in rows:
        # status is the SQLAlchemy enum value
        key = status.value if hasattr(status, "value") else str(status)
        by_status[key] = count

    total = sum(by_status.values())
    chunk_total = (await session.execute(
        select(func.coalesce(func.sum(AskDocsDocument.chunk_count), 0))
        .where(AskDocsDocument.status == AskDocsStatus.indexed)
    )).scalar()

    return {
        "total": total,
        "by_status": by_status,
        "total_chunks": int(chunk_total or 0),
    }


async def _query_30d_stats(session) -> dict[str, Any]:
    # Count + sum + avg latency + p95 latency, all in one query
    row = (await session.execute(text("""
        SELECT
          COUNT(*)                                                      AS count,
          COALESCE(SUM(tokens_used), 0)                                 AS tokens,
          AVG(duration_ms)                                              AS avg_latency,
          PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms)     AS p95_latency
        FROM ask_docs_queries
        WHERE created_at > now() - interval '30 days'
    """))).one()

    by_mode_rows = (await session.execute(text("""
        SELECT llm_mode, COUNT(*) AS count, COALESCE(SUM(tokens_used), 0) AS tokens
        FROM ask_docs_queries
        WHERE created_at > now() - interval '30 days'
        GROUP BY llm_mode
        ORDER BY llm_mode
    """))).all()
    by_mode = [{"mode": r.llm_mode, "count": r.count, "tokens": int(r.tokens)} for r in by_mode_rows]

    # Daily series — generate_series guarantees 30 entries even on empty days
    series_rows = (await session.execute(text("""
        SELECT d::date AS day, COALESCE(SUM(q.tokens_used), 0) AS tokens
        FROM generate_series(
            (now()::date - interval '29 days'),
            now()::date,
            interval '1 day'
        ) d
        LEFT JOIN ask_docs_queries q
          ON q.created_at::date = d::date
         AND q.created_at > now() - interval '30 days'
        GROUP BY d ORDER BY d
    """))).all()
    tokens_per_day = [{"date": r.day.isoformat(), "tokens": int(r.tokens)} for r in series_rows]

    return {
        "count": row.count,
        "tokens": int(row.tokens),
        "by_mode": by_mode,
        "tokens_per_day": tokens_per_day,
        "avg_latency_ms": int(row.avg_latency) if row.avg_latency is not None else None,
        "p95_latency_ms": int(row.p95_latency) if row.p95_latency is not None else None,
        "cost_usd_estimated": 0.0,  # filled by caller after pricing lookup
    }

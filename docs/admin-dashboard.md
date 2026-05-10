# Admin Dashboard Guide

Reading the Ask Docs admin dashboard at `/admin/modules/ask-docs`. Auto-polls every 30 seconds; the "last update" timestamp confirms it's live.

Superuser only. The dashboard is read-only — no actions, just observation.

---

## Top stat cards (4 across)

### Documents

- **Big number:** total documents uploaded (regardless of status)
- **Subtitle:** how many are `indexed` (i.e., available for chat)
- **Drill-down:** see the "Document status" card lower on the page for the full breakdown

If the subtitle is significantly less than the big number, you have docs stuck in `pending`/`indexing`/`failed`. Check the worker logs:

```bash
docker compose logs --tail=100 worker
```

### Queries (30d)

- **Big number:** total chat queries in the last 30 days (rolling window — not calendar month)
- **Subtitle:** average + p95 latency in milliseconds
  - Average = mean of `duration_ms` across the period
  - p95 = 95th-percentile (Postgres `PERCENTILE_CONT(0.95)`)

**Healthy ranges:**
- Avg latency 1500–3000ms (depends on Anthropic API + your network)
- p95 should be < 2× avg; if it's spiking higher, a few queries are running slow (large prompts, slow LLM responses, or the reranker model loading on first use)

### Tokens (30d)

- **Big number:** sum of `tokens_used` across all queries in the window. Format: `8.4K` for thousands, `1.2M` for millions.
- Includes both input + output tokens (per the LLM provider's usage report)

### Estimated cost (30d)

- **Big number:** USD cost estimate, rounded to 4 decimals (so a $0.0029 day shows up vs collapsing to $0.00)
- **Subtitle:** "prices as of YYYY-MM-DD"
- **Tooltip:** explicit "Anthropic pricing may have changed since" disclaimer

**How it's calculated:**
- We don't store the model used per-query (would require a migration)
- We use the currently-configured mode + model from `module_configs` and apply that pricing to the entire 30-day token total
- If you switch from Anthropic to Ollama mid-month, the historical Anthropic spend gets retroactively repriced to Ollama's $0/M

For accurate billing, always check your Anthropic console — this card is a budgeting estimate, not an invoice.

**Pricing source:** hardcoded in `backend/app/modules/ask_docs/pricing.py`. Update + redeploy when Anthropic changes prices.

---

## Token usage chart (last 30 days)

Inline SVG bar chart. Each bar is one day; height proportional to that day's token total.

- **Hover any bar:** tooltip with the date + exact token count
- **Caption shows:** "Max day: N · Total: N" — quick way to spot anomalous spikes
- **Empty days:** render as a 1-pixel bar (so you see the day exists, not a gap)
- **Date range labels:** oldest day on the left, today on the right

**Patterns to watch for:**
- A sudden tall spike on one day = either (a) a power user doing many queries, or (b) someone hammering the system in a tight loop. Click into "Recent queries" to see who.
- A flat-zero pattern after activity = chat is broken. Check the dashboard's mode breakdown card and the recent queries log for errors.

---

## Mode breakdown card (left column, mid-page)

Per-mode counts and token totals for the 30-day window.

Example:

| mode | count | tokens |
|---|---|---|
| anthropic | 215 queries | 78.2K tokens |
| ollama | 2 queries | 241 tokens |

If you see modes you didn't expect (e.g., `ollama` rows after only running Anthropic), someone changed the config mid-window. Cross-reference with the recent-queries log.

If the table says "No queries yet", either nobody's chatted, or all queries failed before the orchestrator could persist a row.

---

## Document status card (right column, mid-page)

Counts of documents in each state:

| Status | Meaning |
|---|---|
| Indexed | Available for chat |
| Indexing | Currently being processed by the worker |
| Pending | Waiting in the worker queue |
| Failed | Indexing crashed; hover the row in `/modules/ask-docs/library` for the error |
| **Total chunks** | Sum of `chunk_count` across all `indexed` docs — the size of the searchable corpus |

If `Pending` is > 0 for more than ~30 seconds, the worker isn't picking jobs up:

```bash
docker compose ps worker         # Should be "Up X minutes (healthy)"
docker compose logs --tail=50 worker
```

If `Failed` is non-zero, every failed doc has a per-row error in the library page.

---

## Recent queries table (last 100)

The newest 100 queries, newest first. Each row:

| Column | What it is |
|---|---|
| Time | When the query was logged (your browser's timezone, short format) |
| User | Email of the user who asked (`—` if user was deleted — FK is ON DELETE SET NULL) |
| Query | First 60 chars of the question; full text on row click |
| Cit | Citation count — how many `[N]` pills the answer used |
| Tok | Total tokens used by the query |
| ms | End-to-end latency (orchestrator wall-clock) |
| Mode | LLM mode used for that query |

**Click any row** → side panel slides in with:
- The full original question
- The full answer (not truncated)
- Mode + tokens + latency + citation count
- **Cited sources** — each cited chunk's filename, page, and full content

Use the side panel to debug: "user complains the answer is wrong" → click their query → look at the cited chunks → see exactly what the LLM had as context.

### Filtering / search

Not built today. The query log is fixed at "last 100 newest first." For deeper analysis, query Postgres directly:

```bash
docker compose exec postgres psql -U portal -d portal -c "
  SELECT created_at, user_id, query_text, citation_count, tokens_used, duration_ms
    FROM ask_docs_queries
    WHERE query_text ILIKE '%pto%'
    ORDER BY created_at DESC
    LIMIT 50;
"
```

Or join with users for emails:

```sql
SELECT q.created_at, u.email, q.query_text, q.citation_count
  FROM ask_docs_queries q
  LEFT JOIN users u ON u.id = q.user_id
  WHERE q.created_at > now() - interval '7 days'
  ORDER BY q.created_at DESC;
```

---

## Update banner slot

Empty in MVP. Future: when the operator console phones in an update notification (e.g., "v0.6.0 available"), it'll render as a banner at the top of the dashboard. For now you'll see nothing here.

---

## What the dashboard does NOT show

- **Per-document query analytics** — "which doc is most cited?" — not built; the data is there (`sources_used` JSONB on each query) but not aggregated. Manual SQL works.
- **Per-user analytics** — "who's asking the most?" — same as above.
- **Cost trend** — single 30-day total only; no chart of cost over time.
- **Anomaly alerts** — no automated alerting on cost spikes, latency regressions, or failure rate. Add Prometheus + Grafana if you want this.

These are P2+ candidates. File a request if any of them block real customer use.

---

## See also

- [ask-docs.md](./ask-docs.md) — operating the module end-to-end
- [troubleshooting.md](./troubleshooting.md) — when the dashboard shows zeros / errors

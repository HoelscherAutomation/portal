# Ask Docs — Operating Guide

Day-to-day operation of the Ask Docs RAG module: managing documents, configuring the LLM backend, switching modes, the reranker, and the chat UX.

For your first install, do [first-run.md](./first-run.md) first.

---

## How Ask Docs works (60-second tour)

1. **Upload** — admin or any authenticated user drops a PDF/DOCX/TXT/MD file via `/modules/ask-docs/library`
2. **Index** — background worker parses → splits into 1024-token chunks (128-token overlap) → generates 768-dim embeddings via local Ollama (`nomic-embed-text`) → stores in Qdrant
3. **Ask** — employee asks a question via `/modules/ask-docs`
4. **Retrieve** — system embeds the question, finds the top-8 most similar chunks in Qdrant (or top-24 → rerank → top-8 if reranking is on)
5. **Answer** — chunks are formatted as numbered sources, sent to the configured LLM with a system prompt requiring `[N]` citations and a "no info" fallback for unanswerable questions
6. **Stream** — response streams back token-by-token via SSE; citation pills become clickable; clicking opens the source chunk in a side panel

The full retrieval pipeline runs server-side. Documents never leave your portal install except as Qdrant search inputs to your configured LLM (which can be local Ollama → never leaves at all).

---

## Managing documents

### Uploading

`/modules/ask-docs/library` — click the upload area or drag a file in.

**Allowed types:** PDF, DOCX, TXT, MD. Other types are refused with a 400.

**Size cap:** 50 MB per file. Larger uploads are refused with a 413. To raise the cap, change `_MAX_UPLOAD_BYTES` in `backend/app/modules/ask_docs/routes.py` (rebuild backend after).

**What happens after upload:**

| Status | What's happening | Typical time |
|---|---|---|
| `pending` | File received + on disk; waiting for the worker to pick it up | < 1 second |
| `indexing` | Worker is parsing, chunking, embedding, writing to Qdrant | 2–60 seconds |
| `indexed` | All chunks in Qdrant; the doc is searchable | — |
| `failed` | Something went wrong; hover for the error | — |

The library page polls every 3 seconds and updates the status badge live.

**Common indexing failures:**

| Error message | Cause | Fix |
|---|---|---|
| `ParserError: Cannot extract text` | Encrypted PDF, scanned PDF without OCR, password-protected DOCX | Run the file through OCR (e.g., `ocrmypdf`) or unlock it before re-uploading |
| `ConnectError: ollama` | Embeddings service down | `docker compose ps ollama` — restart if needed |
| `nomic-embed-text not found` | Model wasn't pulled at first install | `docker compose exec ollama ollama pull nomic-embed-text` |
| `[REDACTED]: HTTP 401 from ...` | LLM provider auth issue (only fires during chat, not indexing) | See [troubleshooting.md](./troubleshooting.md#chat-error-401) |

### Listing + deleting

The library lists every document with: filename, status, chunk count, error (if failed), uploaded-at timestamp.

**Delete** removes both the file from disk AND its vectors from Qdrant. Only the original uploader OR a superuser can delete a doc — other users get 403.

After delete, the chat will no longer cite that document.

### Re-indexing

There's no "re-index" button today. To force re-indexing:
1. Delete the document
2. Re-upload it

(Or, for the whole corpus, see [Bulk re-indexing](#bulk-re-indexing) below.)

---

## Configuring the LLM backend

`/admin/modules/ask-docs/config` — superuser only. Three radio options under "Active mode":

### Mode 1 — Anthropic (cloud, default)

The highest-quality option for most use cases.

**Setup:**
- **API key** — paste your Anthropic key (`sk-ant-api03-...`). Stored encrypted in `module_configs` (Fernet-encrypted under `SECRET_KEY`). The UI shows `••••••••set` after save with a Clear button to wipe it.
- **Model** — defaults to `claude-sonnet-4-6`. Other valid Anthropic model IDs work (e.g., `claude-opus-4-7` for higher quality at ~5× cost).
- **Max answer tokens** — caps response length. 1024 is enough for most chat-style answers; raise to 2048+ if your users routinely ask for long-form answers.

**Cost:** ~$0.005 per query at sonnet-4-6. Monitor on `/admin/modules/ask-docs` (the cost card).

**Test button** — sends a 1-token round-trip ("Say 'ok'.") to verify the key works without persisting. Returns OK + latency, or a redacted error.

### Mode 2 — BYO Ollama (self-hosted)

Free per-query, slower, lower quality on most hardware.

**Setup:**
- **URL** — your Ollama endpoint (e.g., `http://192.168.10.50:11434` for an Ollama running on a different host, or `http://ollama:11434` for the in-portal one)
- **Model** — model name as Ollama knows it (e.g., `llama3.1:8b`). The model must already be pulled into your Ollama instance:
  ```bash
  docker compose exec ollama ollama pull llama3.1:8b
  ```
- **Max answer tokens** — same as Anthropic; controls Ollama's `num_predict` option

**Quality note:** locally-runnable models (8B parameters) lag Claude Sonnet noticeably on synthesis + citation accuracy. Acceptable for low-stakes Q&A, weak for nuanced reasoning. Larger models (70B+) close the gap but need 40 GB+ RAM and a GPU for usable latency.

**Test button** — works same as Anthropic. First request after enabling Ollama mode is slow (model load); subsequent are normal speed.

### Mode 3 — Hoelscher proxy

Coming soon. Managed inference billed by Hoelscher Automation. UI placeholder for now; the radio is disabled.

### Switching modes

Pick the new mode → fill in its settings → **Test [Mode]** → **Save changes**. The next chat query uses the new config.

The chat orchestrator caches the LLM client construction inside `_make_orchestrator()` per request — no restart needed for mode changes to take effect.

---

## Reranker (Advanced)

Off by default. Enable in `/admin/modules/ask-docs/config` → **Advanced** → check "Cross-encoder reranking" → **Save changes**.

**What it does:** Without rerank, Qdrant's vector similarity ranks chunks by embedding cosine — fast, but embeddings can rank a chunk highly that's about a related-but-different topic. The reranker (`Xenova/ms-marco-MiniLM-L-6-v2`) is a cross-encoder that scores `(query, chunk)` pairs directly — slower per-pair but much more accurate. We retrieve top-24 from Qdrant, rerank, keep top-8 for the LLM.

**When to enable:**
- Corpus has 50+ chunks (small corpora don't have enough candidates for reranking to matter)
- Users report citations that are "topically near" but "factually wrong"
- You're OK with +50–200ms per chat query

**One-time costs:**
- ~80 MB ONNX model downloads to the backend container on first chat after enabling (model load adds ~5–10 seconds to that one chat)
- Subsequent chats just pay the per-query rerank latency

**Disable cleanly:** uncheck the box, save. Backend reverts to single-stage retrieval immediately. The cached model stays in memory until backend restarts (~80 MB RAM); next backend recreate frees it.

---

## Reading the chat answers

Every chat answer comes back with:

- **The text answer** with `[1]`, `[2]` citation pills inline
- **A list of citations** (the `[N]` numbers actually used)
- **Source data** for each citation: filename + page + chunk content, accessible by clicking any pill

### What "I don't have enough information to answer that question" means

This is the **hallucination guard**. It fires in two cases:

1. **Retrieval found nothing relevant** — Qdrant returned chunks but none were a good semantic match. The LLM saw the chunks, didn't see anything to cite, and produced a "no info" answer naturally.

2. **The LLM chose to hallucinate** — it produced a substantive answer with NO `[N]` citations. The post-processing detected the missing citations and replaced the answer with the canonical "no info" message. This is intentional: **the system refuses to ship uncited assertions to users**, even at the cost of false negatives.

If you see this message for a question you know the document covers:
- Try rephrasing (semantic search is sensitive to wording)
- Check that the document is `indexed` not `failed` in the library
- Try with the reranker enabled (catches near-miss embeddings)
- Check the "Recent queries" log on the dashboard — if `citation_count` is 0 but `tokens_used` is high, the LLM produced text but no citations (case 2 above)

### Drilling into a query (admin only)

`/admin/modules/ask-docs` → click any row in the "Recent queries" table. A side panel slides in with:

- The full original question
- The full answer (not truncated)
- Mode used + tokens + latency + citation count
- **Cited sources** — each `[N]` chunk's filename, page, and full content

Use this to debug "why did Ask Docs say X?" — the cited sources tell you exactly what context the LLM saw.

---

## Bulk re-indexing

If you change `ASK_DOCS_CHUNK_SIZE_TOKENS` or `ASK_DOCS_CHUNK_OVERLAP_TOKENS`, existing documents stay chunked at the OLD values. To re-index everything at the new chunk size:

```bash
# Mark every document as pending (worker will re-process)
docker compose exec -T postgres psql -U portal -d portal -c "
  UPDATE ask_docs_documents SET status = 'pending', chunk_count = 0;
  -- Optionally clear the Qdrant collection to drop old vectors:
"
# Drop the Qdrant collection so the worker recreates it cleanly
docker compose exec -T backend python -c "
import asyncio
from app.modules.ask_docs.vectorstore import VectorStore
from app.config import get_settings
s = get_settings()
vs = VectorStore(url=s.qdrant_url, collection_name='ask_docs_chunks', vector_size=768)
asyncio.run(vs.delete_collection())
"
```

Worker will pick up the pending documents within ~10 seconds and re-process them at the new chunk size. Library page reflects the progress.

⚠️ Chat queries during the re-index window return "I don't have enough information" since the collection is empty. Schedule for off-hours.

---

## Privacy / data flow summary

For customer trust conversations:

| What | Stays local | Leaves the install |
|---|---|---|
| Uploaded documents (raw bytes) | ✓ | Never |
| Document chunks (text) | ✓ | Sent to LLM as context for each chat (Anthropic mode) — sent to your local Ollama (Ollama mode) |
| User questions | ✓ | Sent to LLM with the chunks (Anthropic mode) — local in Ollama mode |
| LLM answers | ✓ | Returned from the LLM, stored in `ask_docs_queries` |
| LLM API key | ✓ (encrypted at rest in `module_configs`) | Sent to LLM provider as `Authorization` header per request |
| User accounts, query history | ✓ | Never |
| Backups | ✓ | Whatever you do with the tar.gz file |

**Switching to Ollama mode** = nothing leaves the install for chat (embeddings already use local Ollama). For privacy-sensitive customers, BYO Ollama is the right answer.

---

## See also

- [admin-dashboard.md](./admin-dashboard.md) — interpreting the metrics
- [troubleshooting.md](./troubleshooting.md) — common failures + diagnosis
- [security.md](./security.md) — auth, encryption, threat model

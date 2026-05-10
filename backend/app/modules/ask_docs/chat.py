"""Chat orchestrator: retrieve → build prompt → stream LLM → parse citations → persist."""
import logging
import time
from collections.abc import AsyncIterator

import app.database as db_module
from app.models import AskDocsQuery
from app.modules.ask_docs.citations import apply_hallucination_guard, parse_citation_numbers
from app.modules.ask_docs.prompts import SYSTEM_PROMPT, build_user_message
from app.modules.ask_docs.retrieval import retrieve_sources

logger = logging.getLogger(__name__)


class ChatOrchestrator:
    def __init__(
        self,
        *,
        embeddings,
        vectorstore,
        llm,
        llm_mode: str,
        top_k: int,
        max_answer_tokens: int,
    ):
        self._embeddings = embeddings
        self._vectorstore = vectorstore
        self._llm = llm
        self._llm_mode = llm_mode
        self._top_k = top_k
        self._max_answer_tokens = max_answer_tokens

    async def run(self, *, query: str, user_id: int | None) -> AsyncIterator[dict]:
        """Yield events for SSE consumption.

        Events:
          {"type": "sources", "sources": [{number, filename, page_num, content}, ...]}
          {"type": "delta",   "text": "..."}
          {"type": "final",   "answer": "...", "citations": [N, N, ...]}
        """
        started = time.monotonic()

        sources = await retrieve_sources(
            query=query,
            top_k=self._top_k,
            embeddings=self._embeddings,
            vectorstore=self._vectorstore,
        )
        yield {
            "type": "sources",
            "sources": [
                {
                    "number": s.number,
                    "filename": s.filename,
                    "page_num": s.page_num,
                    "content": s.content,
                }
                for s in sources
            ],
        }

        user_message = build_user_message(query, sources)
        usage_holder: dict = {}

        def _capture_usage(u: dict) -> None:
            usage_holder.update(u)

        full_answer = ""
        async for delta in self._llm.stream_chat(
            system=SYSTEM_PROMPT,
            user=user_message,
            max_tokens=self._max_answer_tokens,
            on_final_usage=_capture_usage,
        ):
            full_answer += delta
            yield {"type": "delta", "text": delta}

        max_valid = len(sources) if sources else None
        cited = parse_citation_numbers(full_answer, max_valid=max_valid)
        guarded = apply_hallucination_guard(full_answer, cited)

        duration_ms = int((time.monotonic() - started) * 1000)
        tokens_used = None
        if usage_holder:
            tokens_used = usage_holder.get("input_tokens", 0) + usage_holder.get("output_tokens", 0)

        try:
            async with db_module.async_session_maker() as session:
                entry = AskDocsQuery(
                    user_id=user_id,
                    query_text=query,
                    answer_text=guarded,
                    citation_count=len(cited),
                    llm_mode=self._llm_mode,
                    tokens_used=tokens_used,
                    duration_ms=duration_ms,
                )
                session.add(entry)
                await session.commit()
        except Exception:
            # The answer was already streamed; persistence is non-critical to the user.
            # Log it for the operator and still emit `final` so the SSE stream completes cleanly.
            logger.exception("Failed to persist AskDocsQuery — answer was returned but not logged")

        yield {
            "type": "final",
            "answer": guarded,
            "citations": cited,
        }

    async def close_clients(self) -> None:
        """Best-effort close of underlying httpx-backed clients. Used by the route's finally block.

        Includes the LLM client — both AnthropicChatClient and OllamaChatClient hold
        httpx connection pools that leak otherwise. The hasattr guard tolerates fakes
        in tests + any future ChatClient impl that doesn't need aclose.
        """
        for client in (self._embeddings, self._vectorstore, self._llm):
            if client is None or not hasattr(client, "aclose"):
                continue
            try:
                await client.aclose()
            except Exception:
                logger.exception("Failed to close client")

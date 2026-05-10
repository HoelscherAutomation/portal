"""Cross-encoder rerank wrapper around fastembed's TextCrossEncoder.

Lazy-loads the model on first use (saves ~80MB RAM if rerank is never enabled).
Reuses the same encoder instance across calls — first call has ~5-10s latency
for model download + load, subsequent calls are ~50-200ms for typical top-K.
"""
import logging
from typing import Any

from app.modules.ask_docs.prompts import FormattedSource

logger = logging.getLogger(__name__)


class Reranker:
    """Reorder retrieved sources by cross-encoder relevance score.

    Constructor is cheap — does not import fastembed. The model loads on the
    first non-empty `.rerank()` call. Pass `_encoder=` in tests to inject a
    fake without touching fastembed.
    """

    def __init__(
        self,
        *,
        model_name: str = "Xenova/ms-marco-MiniLM-L-6-v2",
        _encoder: Any | None = None,
    ):
        self._model_name = model_name
        self._encoder = _encoder

    def _ensure_loaded(self) -> None:
        if self._encoder is None:
            logger.info("Loading reranker model %s (first use; ~80MB)", self._model_name)
            from fastembed.rerank.cross_encoder import TextCrossEncoder
            self._encoder = TextCrossEncoder(model_name=self._model_name)

    def rerank(
        self,
        query: str,
        sources: list[FormattedSource],
        top_n: int,
    ) -> list[FormattedSource]:
        """Return at most top_n sources, reordered by descending relevance to query.

        Preserves each source's original `number` so the LLM still cites by the
        same numbering it would have seen pre-rerank.
        """
        if not sources:
            return []
        self._ensure_loaded()
        scores = list(self._encoder.rerank(query, [s.content for s in sources]))
        scored = sorted(zip(scores, sources), key=lambda pair: pair[0], reverse=True)
        return [src for _, src in scored[:top_n]]

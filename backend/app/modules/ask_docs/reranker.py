"""Cross-encoder rerank wrapper around fastembed's TextCrossEncoder.

Lazy-loads the model on first use (saves ~80MB RAM if rerank is never enabled).
Reuses the same encoder instance across calls — first call has ~5-10s latency
for model download + load, subsequent calls are ~50-200ms for typical top-K.

For the cross-process singleton (one model load per backend process, not per
chat request), see `app.modules.ask_docs.routes._get_reranker`.
"""
import logging
from typing import Any

from app.modules.ask_docs.prompts import FormattedSource

logger = logging.getLogger(__name__)


class RerankerUnavailableError(Exception):
    """Raised when the fastembed model cannot be loaded.

    Wraps ImportError (ONNX runtime missing on this arch), OSError /
    ConnectionError (model download failed), or RuntimeError (init crash)
    so the SSE error path can surface a single admin-friendly message
    instead of an unactionable Python traceback in the browser.
    """


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
            try:
                from fastembed.rerank.cross_encoder import TextCrossEncoder
                self._encoder = TextCrossEncoder(model_name=self._model_name)
            except Exception as exc:
                raise RerankerUnavailableError(
                    "Cross-encoder reranking model could not be loaded — disable "
                    "'Cross-encoder reranking' in Ask Docs config or contact support."
                ) from exc

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
        # strict=True catches a model-output bug where the encoder returns a
        # different number of scores than passages — without it, zip would
        # silently truncate and the orchestrator would drop sources.
        scored = sorted(
            zip(scores, sources, strict=True),
            key=lambda pair: pair[0],
            reverse=True,
        )
        return [src for _, src in scored[:top_n]]

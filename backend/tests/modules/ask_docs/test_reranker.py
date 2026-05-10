"""Tests for the cross-encoder Reranker.

Note: tests use a fake encoder injected via the optional `_encoder` param so we
don't load the real ~80MB fastembed model in unit tests. Real model is exercised
in the live E2E (T6).
"""
import sys

import pytest

from app.modules.ask_docs.prompts import FormattedSource
from app.modules.ask_docs.reranker import Reranker


def _src(number: int, content: str) -> FormattedSource:
    return FormattedSource(number=number, filename=f"f{number}.pdf", page_num=1, content=content)


class _FakeEncoder:
    """Fake fastembed cross-encoder returning preset scores per call."""
    def __init__(self, scores: list[float]):
        self._scores = scores
        self.calls: list[tuple[str, list[str]]] = []

    def rerank(self, query: str, passages: list[str]):
        self.calls.append((query, passages))
        return list(self._scores)


def test_lazy_does_not_import_fastembed_on_construction():
    """Reranker.__init__ must not import fastembed — saves ~80MB RAM if rerank never enabled."""
    sys.modules.pop("fastembed.rerank.cross_encoder", None)
    r = Reranker()
    assert "fastembed.rerank.cross_encoder" not in sys.modules
    assert r._encoder is None


def test_rerank_reorders_by_score():
    fake = _FakeEncoder(scores=[0.1, 0.9, 0.5])
    r = Reranker(_encoder=fake)
    sources = [_src(1, "low"), _src(2, "high"), _src(3, "mid")]
    out = r.rerank("query", sources, top_n=3)
    assert [s.number for s in out] == [2, 3, 1]


def test_rerank_returns_at_most_top_n():
    fake = _FakeEncoder(scores=[0.9, 0.8, 0.7, 0.6])
    r = Reranker(_encoder=fake)
    sources = [_src(i, f"c{i}") for i in range(1, 5)]
    out = r.rerank("q", sources, top_n=2)
    assert len(out) == 2
    assert [s.number for s in out] == [1, 2]


def test_rerank_empty_input_returns_empty_without_loading():
    r = Reranker()
    assert r.rerank("q", [], top_n=8) == []
    assert r._encoder is None  # never loaded


def test_rerank_strict_zip_catches_score_count_mismatch():
    """If the encoder ever returns a different number of scores than passages,
    fail loud rather than silently dropping sources via a short zip."""
    fake = _FakeEncoder(scores=[0.5, 0.3])  # only 2 scores
    r = Reranker(_encoder=fake)
    sources = [_src(1, "a"), _src(2, "b"), _src(3, "c")]  # 3 sources
    with pytest.raises(ValueError):  # zip(strict=True) raises ValueError on mismatch
        r.rerank("q", sources, top_n=3)


def test_get_reranker_returns_singleton_across_calls():
    """The module-level singleton in routes._get_reranker must reuse the same
    Reranker instance across chat requests — otherwise the model reloads on every
    request, defeating the entire lazy-load optimization."""
    from app.modules.ask_docs import routes

    routes._reranker_singleton = None  # reset to start clean
    first = routes._get_reranker()
    second = routes._get_reranker()
    assert first is second
    routes._reranker_singleton = None  # cleanup so other tests start clean

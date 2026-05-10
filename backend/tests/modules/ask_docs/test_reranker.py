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

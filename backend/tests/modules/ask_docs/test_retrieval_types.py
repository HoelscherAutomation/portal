from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.modules.ask_docs.retrieval_types import RetrievalFilters, RetrievalQuery


def test_filters_defaults_are_all_none() -> None:
    f = RetrievalFilters()
    assert f.doc_ids is None
    assert f.content_types is None
    assert f.uploaded_by is None
    assert f.uploaded_after is None
    assert f.uploaded_before is None


def test_filters_reject_unknown_field() -> None:
    with pytest.raises(ValidationError):
        RetrievalFilters(filename=["foo.pdf"])  # type: ignore[call-arg]


def test_filters_accept_known_fields() -> None:
    f = RetrievalFilters(
        doc_ids=["abc", "def"],
        content_types=["application/pdf"],
        uploaded_by=[1, 2],
        uploaded_after=datetime(2026, 1, 1, tzinfo=timezone.utc),
        uploaded_before=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    assert f.doc_ids == ["abc", "def"]
    assert f.uploaded_by == [1, 2]


def test_filters_reject_inverted_date_range() -> None:
    with pytest.raises(ValidationError):
        RetrievalFilters(
            uploaded_after=datetime(2026, 6, 1, tzinfo=timezone.utc),
            uploaded_before=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )


def test_filters_reject_equal_date_range() -> None:
    same = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(ValidationError):
        RetrievalFilters(uploaded_after=same, uploaded_before=same)


def test_filters_accept_one_sided_range() -> None:
    f = RetrievalFilters(uploaded_after=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert f.uploaded_before is None


def test_query_requires_non_empty_text() -> None:
    with pytest.raises(ValidationError):
        RetrievalQuery(text="")


def test_query_top_k_bounds() -> None:
    with pytest.raises(ValidationError):
        RetrievalQuery(text="hi", top_k=0)
    with pytest.raises(ValidationError):
        RetrievalQuery(text="hi", top_k=101)


def test_query_defaults() -> None:
    q = RetrievalQuery(text="hello")
    assert q.top_k == 8
    assert isinstance(q.filters, RetrievalFilters)
    assert q.filters.doc_ids is None

from app.modules.ask_docs.citations import (
    HALLUCINATION_GUARD_TEXT,
    apply_hallucination_guard,
    parse_citation_numbers,
)


def test_parse_single_citation():
    nums = parse_citation_numbers("The PTO carryover is 5 days [1].")
    assert nums == [1]


def test_parse_multiple_citations():
    nums = parse_citation_numbers("The policy says X [1] and also Y [2]. See also [3].")
    assert nums == [1, 2, 3]


def test_parse_dedup_preserves_order():
    nums = parse_citation_numbers("X says A [1]. Y also says A [1]. Z says B [2].")
    assert nums == [1, 2]


def test_parse_filters_invalid_numbers():
    nums = parse_citation_numbers("Bogus [99]. Real [3].", max_valid=8)
    assert nums == [3]


def test_parse_no_citations():
    nums = parse_citation_numbers("This answer has no citations at all.")
    assert nums == []


def test_hallucination_guard_replaces_no_citation_substantive_answer():
    answer = "Based on the documents, the policy is to allow 5 days carryover."
    cited = []
    result = apply_hallucination_guard(answer, cited)
    assert result == HALLUCINATION_GUARD_TEXT


def test_hallucination_guard_keeps_explicit_no_info_response():
    answer = "I don't have enough information to answer that question."
    cited = []
    result = apply_hallucination_guard(answer, cited)
    assert result == answer


def test_hallucination_guard_keeps_short_answer_with_citation():
    answer = "Yes [1]."
    cited = [1]
    result = apply_hallucination_guard(answer, cited)
    assert result == answer

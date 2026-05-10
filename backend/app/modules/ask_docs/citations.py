"""Citation parsing + hallucination guard."""
import re

HALLUCINATION_GUARD_TEXT = "I don't have enough information to answer that question."

_CITATION_RE = re.compile(r"\[(\d+)\]")
_SUBSTANTIVE_THRESHOLD = 50  # chars


def parse_citation_numbers(text: str, max_valid: int | None = None) -> list[int]:
    """Extract [N] citation numbers from text, dedup'd, in order of first appearance.

    If max_valid is set, drop numbers > max_valid (LLM hallucinated source numbers).
    """
    seen: set[int] = set()
    out: list[int] = []
    for match in _CITATION_RE.finditer(text):
        n = int(match.group(1))
        if max_valid is not None and (n < 1 or n > max_valid):
            continue
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def apply_hallucination_guard(answer: str, cited_numbers: list[int]) -> str:
    """Replace substantive zero-citation answers with the canonical no-info message."""
    if cited_numbers:
        return answer
    stripped = answer.strip()
    if len(stripped) < _SUBSTANTIVE_THRESHOLD:
        return answer
    if "don't have enough information" in stripped.lower() or "no information" in stripped.lower():
        return answer
    return HALLUCINATION_GUARD_TEXT

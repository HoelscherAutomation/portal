"""LLM prompt templates for Ask Docs chat."""
from dataclasses import dataclass


@dataclass(frozen=True)
class FormattedSource:
    """One source as it appears in the prompt — number + filename + page + content."""
    number: int
    filename: str
    page_num: int
    content: str


SYSTEM_PROMPT = """You are answering questions about a customer's internal documents. \
ONLY use information from the provided sources. Every factual claim MUST cite its \
source as [N] where N is the source number. If the sources don't contain enough \
information to answer the question, respond with exactly: "I don't have enough \
information to answer that question."
"""


def build_user_message(question: str, sources: list[FormattedSource]) -> str:
    """Build the user message with sources block + the question."""
    if not sources:
        sources_block = "(No sources retrieved.)"
    else:
        lines = [
            f"[{s.number}] (from {s.filename}, page {s.page_num}): {s.content}"
            for s in sources
        ]
        sources_block = "\n\n".join(lines)

    return f"Sources:\n\n{sources_block}\n\nQuestion: {question}"

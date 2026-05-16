"""Product-facing retrieval request types.

Translated to Qdrant Filter at the VectorStore boundary so chat orchestrator,
routes, retrieval, and tests never touch Qdrant types directly.
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RetrievalFilters(BaseModel):
    """Optional filter dimensions for a retrieval request."""

    model_config = ConfigDict(extra="forbid")

    doc_ids: list[str] | None = None
    content_types: list[str] | None = None
    uploaded_by: list[int] | None = None
    uploaded_after: datetime | None = None
    uploaded_before: datetime | None = None

    @model_validator(mode="after")
    def _validate_date_range(self) -> "RetrievalFilters":
        if (
            self.uploaded_after is not None
            and self.uploaded_before is not None
            and self.uploaded_after >= self.uploaded_before
        ):
            raise ValueError(
                "uploaded_after must be strictly less than uploaded_before"
            )
        return self


class RetrievalQuery(BaseModel):
    """Full retrieval request: query text, top_k, optional filters."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., min_length=1)
    top_k: int = Field(8, ge=1, le=100)
    filters: RetrievalFilters = Field(default_factory=RetrievalFilters)

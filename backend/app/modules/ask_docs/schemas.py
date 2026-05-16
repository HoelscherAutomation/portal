import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.modules.ask_docs.retrieval_types import RetrievalFilters


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    status: Literal["pending", "indexing", "indexed", "failed"]
    chunk_count: int
    error_message: str | None
    uploaded_at: datetime


class ChatRequest(BaseModel):
    query: str
    filters: RetrievalFilters | None = None

from typing import Literal

from pydantic import BaseModel


class ModuleRead(BaseModel):
    """Combined view: registry def + enablement + pending request flag."""

    key: str
    name: str
    description: str
    status: Literal["live", "preview"]
    target: str
    enabled: bool
    has_pending_request: bool

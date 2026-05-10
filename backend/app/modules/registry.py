"""Code-defined module catalog. Single source of truth for what modules exist.

Edit this file when adding a new module to the roadmap. The DB only tracks
per-tenant enablement state and customer requests, not module definitions.
"""
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ModuleDef:
    key: str          # stable identifier; used in URLs and DB rows
    name: str         # display name
    description: str  # one-line summary
    status: Literal["live", "preview"]
    target: str       # human-readable target window (used for both live + preview)


REGISTRY: tuple[ModuleDef, ...] = (
    ModuleDef(
        key="ask-docs",
        name="Ask Docs",
        description="AI document Q&A with mandatory citations.",
        status="live",
        target="P1 (active)",
    ),
    ModuleDef(
        key="announcements",
        name="Announcements",
        description="Internal company news and updates.",
        status="preview",
        target="Q3 2026",
    ),
    ModuleDef(
        key="employee-directory",
        name="Employee Directory",
        description="Who-is-who reference for the team.",
        status="preview",
        target="Q3 2026",
    ),
    ModuleDef(
        key="onboarding",
        name="Onboarding",
        description="Checklist-driven new-hire ramp.",
        status="preview",
        target="Q4 2026",
    ),
    ModuleDef(
        key="hr-documents",
        name="HR Documents",
        description="Passive document storage (handbooks, signed forms).",
        status="preview",
        target="Q4 2026",
    ),
    ModuleDef(
        key="expense-reports",
        name="Expense Reports",
        description="Submit, approve, track expense reimbursements.",
        status="preview",
        target="Q4 2026",
    ),
    ModuleDef(
        key="forms",
        name="Forms",
        description="Generic catch-all forms with approval routing.",
        status="preview",
        target="2027",
    ),
)


REGISTRY_BY_KEY: dict[str, ModuleDef] = {m.key: m for m in REGISTRY}


def get_module(key: str) -> ModuleDef | None:
    return REGISTRY_BY_KEY.get(key)

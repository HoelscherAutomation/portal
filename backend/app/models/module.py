from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ModuleEnablement(Base):
    """Per-tenant enablement state for one module.

    Row exists only after Hoelscher enables the module via the Operator Console.
    Absence of a row means disabled.
    """

    __tablename__ = "module_enablements"

    module_key: Mapped[str] = mapped_column(String(50), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    enabled_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class ModuleRequest(Base):
    """A customer-admin request to have a module enabled.

    Fulfilled by Hoelscher via the Operator Console (P0d). New rows can only
    be created if no unfulfilled request for the same module already exists.
    """

    __tablename__ = "module_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    module_key: Mapped[str] = mapped_column(String(50), nullable=False)
    requested_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    fulfilled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    fulfilled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

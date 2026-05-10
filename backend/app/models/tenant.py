from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TenantConfig(Base):
    __tablename__ = "tenant_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_name: Mapped[str] = mapped_column(String(120), default="My Company")
    primary_color: Mapped[str] = mapped_column(String(7), default="#6dd5fa")
    logo_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    welcome_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

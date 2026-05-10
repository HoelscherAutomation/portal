from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TenantConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    company_name: str
    primary_color: str
    logo_filename: str | None
    welcome_message: str | None
    updated_at: datetime


class TenantConfigUpdate(BaseModel):
    company_name: str | None = Field(default=None, max_length=120)
    primary_color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    welcome_message: str | None = Field(default=None, max_length=500)

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.backend import current_active_user
from app.database import get_async_session
from app.models import TenantConfig, User
from app.schemas.tenant import TenantConfigRead

router = APIRouter()


@router.get("/config", response_model=TenantConfigRead)
async def read_tenant_config(
    _user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> TenantConfig:
    return await session.get(TenantConfig, 1)

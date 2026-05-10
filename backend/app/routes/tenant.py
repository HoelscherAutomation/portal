from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.backend import current_active_user, current_superuser
from app.database import get_async_session
from app.models import TenantConfig, User
from app.schemas.tenant import TenantConfigRead, TenantConfigUpdate

router = APIRouter()


@router.get("/config", response_model=TenantConfigRead)
async def read_tenant_config(
    _user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> TenantConfig:
    return await session.get(TenantConfig, 1)


@router.put("/config", response_model=TenantConfigRead)
async def update_tenant_config(
    update: TenantConfigUpdate,
    _user: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session),
) -> TenantConfig:
    config = await session.get(TenantConfig, 1)
    for field, value in update.model_dump(exclude_unset=True).items():
        setattr(config, field, value)
    await session.commit()
    await session.refresh(config)
    return config

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.backend import current_active_user, current_superuser
from app.database import get_async_session
from app.models import TenantConfig, User
from app.schemas.tenant import TenantConfigRead, TenantConfigUpdate
from app.services.uploads import InvalidImageError, delete_logo, save_logo

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


@router.post("/logo", response_model=TenantConfigRead)
async def upload_logo(
    file: UploadFile,
    _user: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session),
) -> TenantConfig:
    content = await file.read()
    try:
        filename = await save_logo(content, file.filename or "logo")
    except InvalidImageError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    config = await session.get(TenantConfig, 1)
    if config.logo_filename:
        delete_logo(config.logo_filename)
    config.logo_filename = filename
    await session.commit()
    await session.refresh(config)
    return config

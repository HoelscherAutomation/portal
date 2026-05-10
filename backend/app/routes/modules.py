from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.backend import current_active_user
from app.database import get_async_session
from app.models import ModuleEnablement, ModuleRequest, User
from app.modules.registry import REGISTRY
from app.schemas.module import ModuleRead

router = APIRouter()


@router.get("", response_model=list[ModuleRead])
async def list_modules(
    _user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> list[ModuleRead]:
    enablement_rows = (await session.execute(select(ModuleEnablement))).scalars().all()
    enabled_keys = {row.module_key for row in enablement_rows if row.enabled}

    pending_rows = (
        await session.execute(
            select(ModuleRequest.module_key).where(ModuleRequest.fulfilled.is_(False))
        )
    ).scalars().all()
    pending_keys = set(pending_rows)

    return [
        ModuleRead(
            key=m.key,
            name=m.name,
            description=m.description,
            status=m.status,
            target=m.target,
            enabled=m.key in enabled_keys,
            has_pending_request=m.key in pending_keys,
        )
        for m in REGISTRY
    ]

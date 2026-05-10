from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.backend import current_active_user, current_superuser
from app.database import get_async_session
from app.models import ModuleEnablement, ModuleRequest, User
from app.modules.registry import REGISTRY, get_module
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


@router.post("/{module_key}/request", status_code=status.HTTP_201_CREATED)
async def request_module(
    module_key: str,
    user: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, str]:
    if get_module(module_key) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown module: {module_key}",
        )

    existing_pending = await session.execute(
        select(ModuleRequest).where(
            ModuleRequest.module_key == module_key,
            ModuleRequest.fulfilled.is_(False),
        )
    )
    if existing_pending.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A pending request for this module already exists",
        )

    request = ModuleRequest(module_key=module_key, requested_by=user.id)
    session.add(request)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        # Only convert to 409 if it was the partial unique index we expect
        if "uq_module_requests_pending_per_module" in str(exc.orig):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A pending request for this module already exists",
            )
        # Other IntegrityErrors are unexpected — re-raise so they're logged at 500
        raise
    return {"status": "requested"}

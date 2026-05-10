from fastapi import APIRouter, Depends

from app.auth.backend import current_active_user
from app.auth.schemas import UserRead
from app.models import User

router = APIRouter()


@router.get("/me", response_model=UserRead)
async def read_me(user: User = Depends(current_active_user)) -> User:
    return user

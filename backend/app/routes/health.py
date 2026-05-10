from fastapi import APIRouter

from app.services.phone_home import get_phone_home_status

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "phone_home": get_phone_home_status(),
    }

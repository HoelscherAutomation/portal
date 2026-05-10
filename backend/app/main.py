from fastapi import FastAPI

from app.auth.backend import auth_backend, fastapi_users
from app.auth.schemas import UserRead, UserUpdate
from app.routes import health

app = FastAPI(title="Hoelscher Employee Portal")

app.include_router(health.router, prefix="/api")
app.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/api/auth",
    tags=["auth"],
)
app.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate),
    prefix="/api/users",
    tags=["users"],
)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.backend import auth_backend, fastapi_users
from app.auth.schemas import UserRead, UserUpdate
from app.config import get_settings
from app.routes import health, me, tenant

app = FastAPI(title="Hoelscher Employee Portal")

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(me.router, prefix="/api")
app.include_router(tenant.router, prefix="/api/tenant", tags=["tenant"])
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

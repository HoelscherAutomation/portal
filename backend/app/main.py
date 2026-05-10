from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.auth.backend import auth_backend, fastapi_users
from app.auth.schemas import UserRead, UserUpdate
from app.config import get_settings
from app.database import engine
from app.routes import health, me, modules, tenant
from app.services.uploads import _ensure_uploads_dir


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(title="Hoelscher Employee Portal", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure uploads dir exists at startup, then serve it.
_ensure_uploads_dir()
app.mount("/uploads", StaticFiles(directory=get_settings().uploads_path), name="uploads")

app.include_router(health.router, prefix="/api")
app.include_router(me.router, prefix="/api")
app.include_router(tenant.router, prefix="/api/tenant", tags=["tenant"])
app.include_router(modules.router, prefix="/api/modules", tags=["modules"])
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

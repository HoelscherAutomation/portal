import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.auth.backend import auth_backend, fastapi_users
from app.auth.schemas import UserRead, UserUpdate
from app.config import get_settings
from app.database import async_session_maker, engine
from app.modules.ask_docs.routes import router as ask_docs_router
from app.routes import health, me, modules, tenant
from app.routes.admin_module_config import router as admin_module_config_router
from app.services.uploads import _ensure_uploads_dir

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio
    import time

    # Startup: verify the database is reachable so failures surface early
    # instead of as an opaque 500 on the first request.
    try:
        async with async_session_maker() as session:
            await session.execute(text("SELECT 1"))
    except Exception as exc:
        logger.error("Database connectivity check failed at startup: %s", exc)
        raise

    settings = get_settings()
    phone_home_task = None
    if settings.oc_url and settings.oc_token:
        # Validate the configured OC_URL up front so a typo doesn't degrade into
        # an opaque per-cycle error after the first 30s delay.
        oc_url_valid = False
        try:
            parsed = httpx.URL(settings.oc_url)
            if parsed.scheme not in ("http", "https"):
                raise ValueError(
                    f"OC_URL must use http or https scheme, got: {parsed.scheme!r}"
                )
            oc_url_valid = True
        except (httpx.InvalidURL, ValueError) as exc:
            logger.error("OC_URL is invalid (%s); phone-home disabled", exc)

        if oc_url_valid:
            from app.services.phone_home import phone_home_loop

            logger.info(
                "Phone-home enabled — target=%s, interval=%ss",
                settings.oc_url,
                settings.phone_home_interval_seconds,
            )
            phone_home_task = asyncio.create_task(
                phone_home_loop(
                    oc_url=settings.oc_url,
                    oc_token=settings.oc_token,
                    portal_version=settings.portal_version,
                    interval_seconds=settings.phone_home_interval_seconds,
                    started_at=time.monotonic(),
                )
            )
    elif settings.oc_url and not settings.oc_token:
        logger.warning("OC_URL set but OC_TOKEN missing — phone-home disabled")
    else:
        logger.info("Phone-home not configured (OC_URL unset) — running standalone")

    yield

    if phone_home_task is not None:
        phone_home_task.cancel()
        try:
            await phone_home_task
        except asyncio.CancelledError:
            pass

    await engine.dispose()


app = FastAPI(title="Hoelscher Employee Portal", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure uploads dir exists at startup (must happen before StaticFiles mount).
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
app.include_router(
    ask_docs_router,
    prefix="/api/modules/ask-docs",
    tags=["ask-docs"],
)
app.include_router(admin_module_config_router)

"""Per-module config CRUD with secret encryption + redaction."""
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

import app.database as db_module
from app.models import ModuleConfig
from app.modules._config_schemas import SCHEMAS, SECRET_PATHS
from app.secrets_helper import (
    decrypt,
    is_encrypted_marker,
    unwrap_encrypted_values,
    wrap_secret,
)


class UnknownModuleError(Exception):
    """Raised when a module_key has no registered schema."""


# Compute defaults once per module from the Pydantic schema's instantiation.
DEFAULTS: dict[str, dict] = {key: cls().model_dump() for key, cls in SCHEMAS.items()}


def _get_path(d: dict, path: tuple[str, ...]) -> Any:
    cur: Any = d
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur


def _set_path(d: dict, path: tuple[str, ...], value: Any) -> None:
    cur: Any = d
    for k in path[:-1]:
        if not isinstance(cur.get(k), dict):
            cur[k] = {}
        cur = cur[k]
    cur[path[-1]] = value


async def _load_in_session(session: AsyncSession, module_key: str) -> dict:
    """Load + decrypt a config inside an existing session. Returns defaults if no row."""
    row = (await session.execute(
        select(ModuleConfig).where(ModuleConfig.module_key == module_key)
    )).scalar_one_or_none()
    if row is None:
        return {**DEFAULTS[module_key]}
    return unwrap_encrypted_values(row.config)


async def load_config(module_key: str) -> dict:
    """Load the persisted config + decrypt secrets. Returns defaults if no row exists."""
    if module_key not in SCHEMAS:
        raise UnknownModuleError(module_key)
    async with db_module.async_session_maker() as session:
        return await _load_in_session(session, module_key)


async def save_config(module_key: str, payload: dict, *, updated_by: int | None) -> dict:
    """Validate via Pydantic, encrypt secret paths, upsert. Returns the validated payload (plaintext).

    Uses a single session for the existing-value read AND the upsert so a concurrent
    save can't race the {_set: true} sentinel resolution within this connection's
    transaction window. Cross-connection concurrent saves still last-writer-win,
    which is acceptable for an admin-only config (rare writes, single user).
    """
    if module_key not in SCHEMAS:
        raise UnknownModuleError(module_key)

    async with db_module.async_session_maker() as session:
        existing = await _load_in_session(session, module_key)
        resolved = _resolve_set_sentinels(payload, existing, SECRET_PATHS.get(module_key, []))

        schema = SCHEMAS[module_key]
        validated = schema(**resolved).model_dump()

        # Encrypt secret-path values in-place before persisting.
        to_persist = {**validated}
        for path in SECRET_PATHS.get(module_key, []):
            plain = _get_path(to_persist, path)
            if plain is None or plain == "":
                continue
            _set_path(to_persist, path, wrap_secret(plain))

        # Explicitly set updated_at in the conflict clause — SQLAlchemy's onupdate=func.now()
        # ORM hook does NOT fire for dialect-level INSERT ... ON CONFLICT.
        stmt = pg_insert(ModuleConfig).values(
            module_key=module_key,
            config=to_persist,
            updated_by=updated_by,
        ).on_conflict_do_update(
            index_elements=["module_key"],
            set_={"config": to_persist, "updated_by": updated_by, "updated_at": func.now()},
        )
        await session.execute(stmt)
        await session.commit()

    return validated


def _resolve_set_sentinels(payload: dict, existing: dict, secret_paths: list[tuple[str, ...]]) -> dict:
    """Replace any {"_set": true} sentinels in secret paths with the existing persisted value."""
    out = {**payload}
    for path in secret_paths:
        incoming = _get_path(out, path)
        if isinstance(incoming, dict) and incoming.get("_set") is True:
            _set_path(out, path, _get_path(existing, path))
    return out


def redact_for_response(config: dict, module_key: str) -> dict:
    """Return a copy with secret-path values replaced by `{"_set": true|false}` markers."""
    out = _deep_copy_no_encrypted(config)
    for path in SECRET_PATHS.get(module_key, []):
        value = _get_path(out, path)
        # Treat None, empty string, and absent as "not set"
        is_set = value not in (None, "")
        _set_path(out, path, {"_set": is_set})
    return out


def _deep_copy_no_encrypted(value: Any) -> Any:
    """Deep-copy, replacing any encrypted markers with their plaintext (used before redact)."""
    if is_encrypted_marker(value):
        return decrypt(value["value"])
    if isinstance(value, dict):
        return {k: _deep_copy_no_encrypted(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_deep_copy_no_encrypted(v) for v in value]
    return value

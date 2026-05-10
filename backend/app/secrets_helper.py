"""Fernet-based field-level encryption for module config secrets.

Key derivation: SECRET_KEY -> HKDF-SHA256 -> 32 bytes -> urlsafe base64 -> Fernet key.
Same SECRET_KEY underpins session cookies, so any process that can decrypt sessions
can decrypt secrets - same trust boundary.
"""
import base64
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config import get_settings


class DecryptionError(Exception):
    """Raised when ciphertext is invalid, tampered, or encrypted with a different key."""


def _fernet() -> Fernet:
    secret = get_settings().secret_key.encode("utf-8")
    derived = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"hoelscher-automation-module-config-v1",
        info=b"module-config-secrets",
    ).derive(secret)
    return Fernet(base64.urlsafe_b64encode(derived))


def encrypt(plaintext: str) -> str:
    """Encrypt a string. Returns a urlsafe-base64 token."""
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt(ciphertext: str) -> str:
    """Decrypt a token. Raises DecryptionError if invalid."""
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise DecryptionError(str(exc)) from exc


def wrap_secret(plaintext: str) -> dict:
    """Wrap a plaintext string into the encrypted-marker dict format."""
    return {"_encrypted": True, "value": encrypt(plaintext)}


def is_encrypted_marker(value: Any) -> bool:
    """True iff value is a dict shaped like an encrypted marker."""
    return (
        isinstance(value, dict)
        and value.get("_encrypted") is True
        and isinstance(value.get("value"), str)
    )


def unwrap_encrypted_values(value: Any) -> Any:
    """Recursively walk a structure, replacing any encrypted markers with their plaintext."""
    if is_encrypted_marker(value):
        return decrypt(value["value"])
    if isinstance(value, dict):
        return {k: unwrap_encrypted_values(v) for k, v in value.items()}
    if isinstance(value, list):
        return [unwrap_encrypted_values(v) for v in value]
    return value

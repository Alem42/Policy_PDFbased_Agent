"""Encrypt provider API keys at rest; plaintext exists only in process memory.

Values are Fernet tokens (AES-128-CBC + HMAC-SHA256) prefixed with ``enc:v1:``.
The key comes from SETTINGS_ENCRYPTION_KEY, or a file generated on first use in
the secrets directory. It is separate from the token-signing APP_SECRET, so
rotating one never invalidates the other.
"""

import logging
import os
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

PREFIX = "enc:v1:"
logger = logging.getLogger(__name__)


@lru_cache
def _fernet() -> Fernet:
    settings = get_settings()
    if settings.settings_encryption_key:
        return Fernet(settings.settings_encryption_key.encode("ascii"))
    path = settings.settings_key_path
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        pass
    else:
        with os.fdopen(descriptor, "wb") as key_file:
            key_file.write(Fernet.generate_key())
    return Fernet(path.read_bytes().strip())


def is_encrypted(value: str | None) -> bool:
    return bool(value) and value.startswith(PREFIX)


def encrypt(value: str | None) -> str | None:
    if not value or is_encrypted(value):
        return value
    return PREFIX + _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt(value: str | None) -> str | None:
    """Return the plaintext; legacy plaintext values pass through unchanged."""
    if not is_encrypted(value):
        return value
    try:
        return _fernet().decrypt(value[len(PREFIX) :].encode("ascii")).decode("utf-8")
    except InvalidToken:
        # A lost or replaced key must not crash the app; the key reads as unset
        # and the administrator re-enters it in Manage.
        logger.error(
            "A stored API key cannot be decrypted with %s. It was encrypted with a "
            "different key; re-enter the API keys under Manage.",
            get_settings().settings_key_path,
        )
        return ""


def reset_cache() -> None:
    _fernet.cache_clear()

"""Symmetric encryption for at-rest secrets (Slack bot tokens, etc.).

Uses ``cryptography.fernet.Fernet``:

- AES-128-CBC + HMAC-SHA-256 with PKCS7 padding
- IVs are random per encryption; the same plaintext encrypts to different
  ciphertexts each call
- Key rotation is supported via ``MultiFernet`` if we ever need it (V3)

``ENCRYPTION_KEY`` in ``.env`` MUST be a URL-safe base64-encoded 32-byte
key — the exact output of ``Fernet.generate_key()``. Generate one with::

    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

The key is loaded once at process start; rotating it requires re-encrypting
all stored ciphertexts (no implicit re-key on read).
"""
from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from apps.api.config import settings


class CryptoError(RuntimeError):
    """ENCRYPTION_KEY is missing, malformed, or the ciphertext is corrupt."""


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    key = settings.encryption_key
    if not key:
        raise CryptoError(
            "ENCRYPTION_KEY is not set. Generate one with: "
            "python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\""
        )
    try:
        return Fernet(key.encode("utf-8") if isinstance(key, str) else key)
    except Exception as exc:  # noqa: BLE001
        raise CryptoError(
            "ENCRYPTION_KEY is malformed — must be a 32-byte url-safe "
            f"base64 key (Fernet.generate_key() output). Underlying error: {exc}"
        ) from exc


def encrypt(plaintext: str) -> str:
    """Return URL-safe base64 ciphertext. Empty string returns empty string."""
    if not plaintext:
        return ""
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt(ciphertext: str) -> str:
    """Return plaintext. Empty input returns empty string. Raises CryptoError
    if the ciphertext was tampered or encrypted with a different key."""
    if not ciphertext:
        return ""
    try:
        return _fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise CryptoError(
            "Decryption failed — ciphertext is corrupt or was encrypted "
            "with a different ENCRYPTION_KEY."
        ) from exc

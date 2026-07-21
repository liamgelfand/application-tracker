from __future__ import annotations

from cryptography.fernet import Fernet

from ..config import settings


def _load_or_create_key() -> bytes:
    """Return the Fernet key, honoring APP_SECRET_KEY or a stored key file."""
    if settings.app_secret_key:
        return settings.app_secret_key.encode()

    key_file = settings.secret_key_file
    if key_file.exists():
        return key_file.read_bytes()

    key = Fernet.generate_key()
    key_file.write_bytes(key)
    # Best-effort tighten permissions (no-op on some platforms).
    try:
        key_file.chmod(0o600)
    except OSError:
        pass
    return key


_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(_load_or_create_key())
    return _fernet


def encrypt(plaintext: str | None) -> str | None:
    """Encrypt a secret for storage. Returns None for empty input."""
    if not plaintext:
        return None
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str | None) -> str | None:
    """Decrypt a stored secret. Returns None for empty input."""
    if not ciphertext:
        return None
    return _get_fernet().decrypt(ciphertext.encode()).decode()

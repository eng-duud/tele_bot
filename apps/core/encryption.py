import base64
import os

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def _get_fernet() -> Fernet:
    """Return the configured Fernet cipher.

    A random fallback is deliberately not used: encryption must remain stable
    across process restarts, deployments, and Celery workers.
    """
    key = getattr(settings, 'DATA_ENCRYPTION_KEY', '') or os.getenv('DATA_ENCRYPTION_KEY', '')
    if not key:
        raise ImproperlyConfigured(
            'DATA_ENCRYPTION_KEY must be configured before encrypted inventory can be used.'
        )

    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except (TypeError, ValueError) as exc:
        raise ImproperlyConfigured(
            'DATA_ENCRYPTION_KEY is not a valid Fernet key. Generate one with '
            "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        ) from exc


def encrypt_data(plain_text: str) -> str:
    """Encrypt a plaintext string and return the ciphertext."""
    if not plain_text:
        return ''
    return _get_fernet().encrypt(plain_text.encode('utf-8')).decode('utf-8')


def decrypt_data(cipher_text: str) -> str:
    """Decrypt ciphertext and fail loudly instead of returning fake stock data."""
    if not cipher_text:
        return ''
    try:
        return _get_fernet().decrypt(cipher_text.encode('utf-8')).decode('utf-8')
    except InvalidToken as exc:
        raise ValueError(
            'Unable to decrypt inventory data. Verify that DATA_ENCRYPTION_KEY '
            'is the same key used when the item was encrypted.'
        ) from exc

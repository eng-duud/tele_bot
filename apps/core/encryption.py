import base64
import os
from cryptography.fernet import Fernet
from django.conf import settings

def _get_fernet() -> Fernet:
    """Retrieve or generate a valid Fernet cipher instance."""
    key = getattr(settings, 'DATA_ENCRYPTION_KEY', '') or os.getenv('DATA_ENCRYPTION_KEY', '')
    if not key:
        # Fallback predictable key for dev if unset
        key = Fernet.generate_key().decode()
    
    # Ensure key is valid Fernet 32-byte url-safe base64 string
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception:
        # If invalid format, pad or hash into 32 url-safe base64 bytes
        import hashlib
        h = hashlib.sha256(str(key).encode()).digest()
        safe_key = base64.urlsafe_b64encode(h)
        return Fernet(safe_key)

def encrypt_data(plain_text: str) -> str:
    """Encrypt a plaintext string and return base64 encoded ciphertext string."""
    if not plain_text:
        return ""
    fernet = _get_fernet()
    encrypted = fernet.encrypt(plain_text.encode('utf-8'))
    return encrypted.decode('utf-8')

def decrypt_data(cipher_text: str) -> str:
    """Decrypt a base64 encoded ciphertext string and return plaintext string."""
    if not cipher_text:
        return ""
    try:
        fernet = _get_fernet()
        decrypted = fernet.decrypt(cipher_text.encode('utf-8'))
        return decrypted.decode('utf-8')
    except Exception:
        # Return fallback or empty if decryption fails to avoid hard crash
        return "[خطأ في فك التشفير]"

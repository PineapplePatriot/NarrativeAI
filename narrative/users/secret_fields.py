"""API keys encrypted in the database: anyone who reads the database file (a backup, the Railway volume) sees
only ciphertext. The encryption key comes from DJANGO_SECRET_KEY, so changing that makes saved keys unreadable:
people then paste their key again (the app treats an unreadable key as no key)."""
import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models

log = logging.getLogger(__name__)
PREFIX = "enc1:"  # values saved before encryption have no prefix and are read as they are


def _fernet():
    digest = hashlib.sha256(b"narrativeai api keys|" + settings.SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(text):
    if not text or text.startswith(PREFIX):
        return text
    return PREFIX + _fernet().encrypt(text.encode()).decode()


def decrypt(stored):
    if not stored or not stored.startswith(PREFIX):
        return stored
    try:
        return _fernet().decrypt(stored[len(PREFIX):].encode()).decode()
    except InvalidToken:
        log.warning("A saved API key can't be decrypted (DJANGO_SECRET_KEY changed?); treating it as empty.")
        return ""


class EncryptedCharField(models.CharField):
    """A CharField whose value is encrypted on save and decrypted on load; code only ever sees plain text."""

    def from_db_value(self, value, expression, connection):
        return decrypt(value)

    def get_prep_value(self, value):
        return encrypt(super().get_prep_value(value))

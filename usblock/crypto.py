"""Key derivation and authenticated encryption for usblock.

The decryption key is derived from the USB hardware serial (the "key") plus
an optional passphrase, using PBKDF2-HMAC-SHA256. Content is encrypted with
AES-256-GCM, which is authenticated: tampering or a wrong key fails loudly
instead of returning garbage.

Design notes / honest limits:
  * The salt lives in the manifest in cleartext. That is fine and normal --
    a salt is not a secret; it only stops precomputed-table attacks.
  * Security rests on the attacker not knowing the serial + passphrase. The
    serial can be read by anyone who has the physical USB, so a passphrase
    is strongly recommended for anything sensitive. Without one, this stops
    copy-and-open on a *different* stick, not a determined local attacker.
"""

from __future__ import annotations

import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

KDF_ITERATIONS = 480_000
KEY_LEN = 32          # AES-256
SALT_LEN = 16
NONCE_LEN = 12        # GCM standard


class WrongKeyError(Exception):
    """Raised when decryption fails: wrong USB, wrong passphrase, or tampering."""


def new_salt() -> bytes:
    return os.urandom(SALT_LEN)


def derive_key(serial: str, passphrase: str, salt: bytes) -> bytes:
    """Derive a 32-byte AES key from the USB serial and optional passphrase."""
    material = f"{serial.strip()}\x00{passphrase}".encode("utf-8")
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=KEY_LEN,
        salt=salt,
        iterations=KDF_ITERATIONS,
    )
    return kdf.derive(material)


def encrypt(key: bytes, plaintext: bytes, associated: bytes = b"") -> bytes:
    """Return nonce || ciphertext(+tag)."""
    nonce = os.urandom(NONCE_LEN)
    ct = AESGCM(key).encrypt(nonce, plaintext, associated)
    return nonce + ct


def decrypt(key: bytes, blob: bytes, associated: bytes = b"") -> bytes:
    """Inverse of encrypt(). Raises WrongKeyError on any failure."""
    if len(blob) < NONCE_LEN + 16:
        raise WrongKeyError("ciphertext too short / corrupt")
    nonce, ct = blob[:NONCE_LEN], blob[NONCE_LEN:]
    try:
        return AESGCM(key).decrypt(nonce, ct, associated)
    except Exception as exc:  # cryptography raises InvalidTag etc.
        raise WrongKeyError(
            "decryption failed — wrong USB drive, wrong passphrase, or the "
            "content was modified"
        ) from exc


# A short known-plaintext token lets the viewer verify the key up front and
# show a clean "wrong USB / wrong passphrase" message instead of failing
# halfway through opening a file.
VERIFY_PLAINTEXT = b"usblock-verify-v1"


def make_verify_token(key: bytes) -> str:
    from base64 import b64encode

    return b64encode(encrypt(key, VERIFY_PLAINTEXT)).decode("ascii")


def check_verify_token(key: bytes, token: str) -> bool:
    from base64 import b64decode

    try:
        return decrypt(key, b64decode(token)) == VERIFY_PLAINTEXT
    except WrongKeyError:
        return False

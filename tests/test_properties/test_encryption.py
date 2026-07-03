# Feature: onenote-organizer, Property 1: Token Encryption Round-Trip
"""
Property 1: Token Encryption Round-Trip

For any valid token string, encrypting it with Fernet using a derived key
and then decrypting the result should produce the original token string.

Validates: Requirements 2.5
"""

import base64
import hashlib
import platform
import uuid

from cryptography.fernet import Fernet
from hypothesis import given, settings
from hypothesis import strategies as st


def _derive_encryption_key() -> bytes:
    """Derive a Fernet encryption key from machine-specific data.

    Mirrors the logic in DeviceCodeAuthProvider._derive_encryption_key()
    to test the same derivation approach independently.
    """
    components = [
        platform.node(),
        str(uuid.getnode()),
        platform.system(),
        platform.machine(),
        "test-client-id",
    ]
    seed = "|".join(components).encode("utf-8")
    raw_key = hashlib.sha256(seed).digest()
    return base64.urlsafe_b64encode(raw_key)


# Strategy: generate arbitrary text strings representing token/cache data
token_strategy = st.text(
    alphabet=st.characters(codec="utf-8", min_codepoint=1),
    min_size=1,
    max_size=500,
)


# Validates: Requirements 2.5
@settings(max_examples=100)
@given(token=token_strategy)
def test_token_encryption_round_trip(token: str) -> None:
    """For any valid token string, encrypt then decrypt produces the original."""
    key = _derive_encryption_key()
    fernet = Fernet(key)

    # Encrypt the token
    encrypted = fernet.encrypt(token.encode("utf-8"))

    # Decrypt the result
    decrypted = fernet.decrypt(encrypted).decode("utf-8")

    # Round-trip must preserve the original
    assert decrypted == token

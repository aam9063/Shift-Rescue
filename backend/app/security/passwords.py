"""Password hashing for manager login (spec §7.5): Argon2id via argon2-cffi.

Fail closed: any verification problem (bad hash format, mismatch, unexpected
error) answers "not authenticated". The legacy seed placeholder
`demo-not-a-real-hash` is not a hash at all and never authenticates anything.
Nothing about the password or its hash is ever logged.
"""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# The pre-auth seed placeholder: present only so old databases fail closed
# loudly instead of matching an empty/dummy password.
LEGACY_PLACEHOLDER_HASH = "demo-not-a-real-hash"

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Hash a password with Argon2id (salted, constant parameters)."""
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against a stored Argon2 hash; True only on a match."""
    if password_hash == LEGACY_PLACEHOLDER_HASH:
        return False
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError, VerificationError):
        return False
    except Exception:  # pragma: no cover - fail closed on any unexpected error
        return False

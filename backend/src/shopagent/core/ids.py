"""Identifier generators: UUIDv7 and Crockford Base32 readable non-sequential codes."""

import secrets
import uuid

# Crockford Base32 alphabet (excludes I, L, O, U to avoid human transcription confusion)
CROCKFORD_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def generate_crockford_code(prefix: str, length: int = 6) -> str:
    """Generate a non-sequential Crockford Base32 code with a prefix (e.g. SL-7K3M9Q).

    32^6 = 1,073,741,824 combinations.
    """
    random_chars = "".join(secrets.choice(CROCKFORD_ALPHABET) for _ in range(length))
    return f"{prefix}-{random_chars}"


def generate_order_code() -> str:
    return generate_crockford_code("SL")


def generate_return_code() -> str:
    return generate_crockford_code("RT")


def generate_refund_code() -> str:
    return generate_crockford_code("RF")


def generate_ticket_code() -> str:
    return generate_crockford_code("TK")


def generate_action_code() -> str:
    return generate_crockford_code("PA")


def generate_uuid() -> uuid.UUID:
    """Generate UUID.

    Uses uuid7 if available in Python 3.14+, otherwise standard uuid4.
    """
    if hasattr(uuid, "uuid7"):
        u7 = uuid.uuid7()
        if isinstance(u7, uuid.UUID):
            return u7
    return uuid.uuid4()

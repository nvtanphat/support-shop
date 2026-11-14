"""Security utilities: password hashing, JWT, preview_hash, and PII masking."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_ph = PasswordHasher()


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, password)
    except VerifyMismatchError:
        return False


def create_jwt_token(
    payload: dict[str, Any], secret: str, expires_delta: timedelta
) -> str:
    to_encode = payload.copy()
    now_utc = datetime.now(ZoneInfo("UTC"))
    to_encode.update({"iat": now_utc, "exp": now_utc + expires_delta})
    return jwt.encode(to_encode, secret, algorithm="HS256")


def decode_jwt_token(token: str, secret: str) -> dict[str, Any]:
    return jwt.decode(token, secret, algorithms=["HS256"])


def create_access_token(data: dict[str, Any]) -> str:
    """Create a standard access JWT token using settings config."""
    from shopagent.core.config import get_settings

    settings = get_settings()
    expires = timedelta(minutes=settings.JWT_ACCESS_EXPIRE_MINUTES)
    return create_jwt_token(data, settings.JWT_SECRET, expires)


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode a standard access JWT token using settings secret."""
    from shopagent.core.config import get_settings

    settings = get_settings()
    return decode_jwt_token(token, settings.JWT_SECRET)


def compute_preview_hash(preview_payload: dict[str, Any]) -> str:
    """Compute deterministic SHA-256 hash of proposal preview payload.

    Used to verify customer confirmed the exact terms shown on card.
    """
    canonical_json = json.dumps(preview_payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


# PII Masking RegEx Patterns
PHONE_PATTERN = re.compile(r"(\+?84|0)(3|5|7|8|9)[0-9]{8}\b")
CARD_PATTERN = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
CCCD_PATTERN = re.compile(r"\b\d{12}\b")


def mask_phone(phone: str) -> str:
    """Show only last 3 digits, e.g. 0912345678 -> ***678."""
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 3:
        return "***"
    return f"***{digits[-3:]}"


def mask_email(email: str) -> str:
    """Mask email, e.g. lan.pham@example.test -> l***m@example.test."""
    parts = email.split("@")
    if len(parts) != 2:
        return "***"
    user, domain = parts
    masked_user = f"{user[0]}***" if len(user) <= 2 else f"{user[0]}***{user[-1]}"
    return f"{masked_user}@{domain}"


def mask_sensitive_numbers(text: str) -> str:
    """Redact payment card and citizen ID numbers, which must never reach the model or the stored history."""
    text = CARD_PATTERN.sub("[SỐ_THẺ_ĐÃ_CHE]", text)
    return CCCD_PATTERN.sub("[CCCD_ĐÃ_CHE]", text)


def mask_pii_text(text: str) -> str:
    """Also mask Vietnamese phone numbers (to their last three digits), on top of cards and citizen IDs."""
    return PHONE_PATTERN.sub(lambda m: mask_phone(m.group(0)), mask_sensitive_numbers(text))


def sanitize_markdown_links(text: str, allowed_domains: list[str]) -> str:
    """Remove or disarm links that do not point to allowed domains."""
    link_pattern = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")

    def _replace_link(m: re.Match[str]) -> str:
        label = m.group(1)
        url = m.group(2)
        # Check domain
        match = re.search(r"https?://([^/:]+)", url)
        if match:
            domain = match.group(1).lower()
            if any(domain == d or domain.endswith("." + d) for d in allowed_domains):
                return m.group(0)
        # Not allowed: keep label only
        return f"{label} ({url})"

    return link_pattern.sub(_replace_link, text)

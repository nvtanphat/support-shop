"""Policy chunking and Vietnamese text normalization."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import uuid
from typing import Any


def remove_vietnamese_accents(text: str) -> str:
    """Normalize and strip Vietnamese diacritics for lexical robust search."""
    # Decomposition
    text = unicodedata.normalize("NFD", text)
    # Remove combining marks
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    # Replace special Vietnamese characters like đ, Đ
    text = text.replace("đ", "d").replace("Đ", "D")
    return unicodedata.normalize("NFC", text).lower()


def tokenize_unaccent(text: str) -> list[str]:
    """Tokenize normalized unaccented text into alphanumeric words."""
    cleaned = remove_vietnamese_accents(text)
    return [w for w in re.findall(r"\w+", cleaned) if len(w) > 1]


def content_hash(clause: dict[str, Any]) -> str:
    """Fingerprint of everything that changes what a customer would be told or when it applies.

    The indexer re-embeds and rewrites a chunk only when this differs from the stored value.
    """
    payload = {
        "text": clause["text"],
        "topic": clause["topic"],
        "title": clause.get("title"),
        "category_scope": sorted(clause.get("category_scope") or ["all"]),
        "version": str(clause.get("version", "2026-11-01")),
        "effective_from": str(clause.get("effective_from")),
        "effective_to": str(clause.get("effective_to")),
        "parent_id": clause.get("parent_id"),
        "status": clause.get("status", "active"),
        "source": clause.get("source", "rules.yaml"),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def build_chunks_from_clauses(clauses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert clauses into structured chunk records ready for indexing."""
    chunks = []
    for c in clauses:
        raw_text = c["text"]
        unaccent_text = remove_vietnamese_accents(raw_text)
        chunks.append({
            "id": uuid.uuid4(),
            "clause_id": c["clause_id"],
            "topic": c["topic"],
            "title": c.get("title"),
            "parent_id": c.get("parent_id"),
            "source": c.get("source", "rules.yaml"),
            "status": c.get("status", "active"),
            "category_scope": c.get("category_scope", ["all"]),
            "version": c.get("version", "2026-11-01"),
            "effective_from": c.get("effective_from"),
            "effective_to": c.get("effective_to"),
            "text": raw_text,
            "text_unaccent": unaccent_text,
            "tokens": tokenize_unaccent(raw_text),
            "content_hash": content_hash(c),
        })
    return chunks

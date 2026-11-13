"""Test doubles shared by several test modules."""

from __future__ import annotations

import hashlib


class FakeEmbedder:
    """Deterministic stand-in for BGE-M3 that records what it was asked to embed."""

    def __init__(self, name: str = "fake") -> None:
        self.name = name
        self.documents: list[str] = []
        self.queries: list[str] = []

    @staticmethod
    def _vector(text: str) -> list[float]:
        return [b / 255 for b in hashlib.sha256(text.encode()).digest()[:8]]

    def embed_documents(self, texts):  # type: ignore[no-untyped-def]
        self.documents.extend(texts)
        return [self._vector(t) for t in texts]

    def embed_query(self, text):  # type: ignore[no-untyped-def]
        self.queries.append(text)
        return self._vector(text)

"""Embedding providers for policy semantic retrieval."""

from __future__ import annotations

import math
from collections.abc import Sequence

from shopagent.rag.chunker import remove_vietnamese_accents, tokenize_unaccent


class BaseEmbeddingProvider:
    """Base interface for policy embeddings."""

    def embed_query(self, text: str) -> list[float]:
        raise NotImplementedError

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        raise NotImplementedError


class FastLexicalEmbedding(BaseEmbeddingProvider):
    """Deterministic, fast character and word n-gram frequency embedding.
    Runs 100% offline, zero network latency, robust to Vietnamese typos and abbreviations.
    """

    def __init__(self, dim: int = 128) -> None:
        self.dim = dim

    def _hash_feature(self, feat: str) -> int:
        h = 2166136261
        for ch in feat:
            h = (h ^ ord(ch)) * 16777619
        return (h & 0x7FFFFFFF) % self.dim

    def _vectorize(self, text: str) -> list[float]:
        norm = remove_vietnamese_accents(text)
        tokens = tokenize_unaccent(norm)
        vec = [0.0] * self.dim

        # 1. Word tokens
        for t in tokens:
            idx = self._hash_feature(t)
            vec[idx] += 1.0

        # 2. Character 3-grams
        cleaned = "".join(tokens)
        for i in range(max(0, len(cleaned) - 2)):
            tri = cleaned[i : i + 3]
            idx = self._hash_feature(tri)
            vec[idx] += 0.5

        # L2 normalize
        norm_val = math.sqrt(sum(v * v for v in vec))
        if norm_val > 0:
            vec = [v / norm_val for v in vec]
        return vec

    def embed_query(self, text: str) -> list[float]:
        return self._vectorize(text)

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vectorize(t) for t in texts]


def get_embedding_provider() -> BaseEmbeddingProvider:
    """Instantiate configured embedding provider."""
    return FastLexicalEmbedding()

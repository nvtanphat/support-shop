"""Dense embeddings for policy retrieval: BGE-M3 (int8 by default) through fastembed (ONNX, CPU).

The dense score is the second signal of the hybrid candidate stage (rag/retriever.py), next to BM25. It
understands paraphrase and slang ("xài thử thấy không hợp" ~ "đổi ý") that share no words with the clause.
Typing without diacritics hurts it badly on its own (Recall@4 drops to 50-80%), which is why the retriever
restores diacritics before embedding the query and keeps BM25 in the fusion.

The model is configured in config/app.yaml (retrieval.embedding) and can be switched off with
RETRIEVAL_EMBEDDING_ENABLED=false; the retriever then runs BM25 only. Needs the `rerank` extra (fastembed).
"""

from __future__ import annotations

import math
import threading
from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from shopagent.core.config import get_app_config, get_settings, model_cache_dir
from shopagent.rag import bge_m3

QUERY_CACHE_SIZE = 512

class Embedder(Protocol):
    name: str

    def embed_query(self, text: str) -> list[float]: ...

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...


class FastEmbedEmbedder:
    """Sentence embeddings from a fastembed model; query vectors are cached because chat repeats itself."""

    def __init__(self, model_name: str) -> None:
        from fastembed import TextEmbedding

        if bge_m3.is_bge_m3(model_name):
            bge_m3.register(model_name)
        self.name = model_name
        self._model = TextEmbedding(model_name=model_name, cache_dir=model_cache_dir())
        self._lock = threading.Lock()  # one ONNX session; calls come from worker threads
        self._queries: OrderedDict[str, list[float]] = OrderedDict()

    def _embed(self, texts: Sequence[str]) -> list[list[float]]:
        with self._lock:
            return [[float(x) for x in vector] for vector in self._model.embed(list(texts))]

    def embed_query(self, text: str) -> list[float]:
        cached = self._queries.get(text)
        if cached is not None:
            self._queries.move_to_end(text)
            return cached
        vector = self._embed([text])[0]
        self._queries[text] = vector
        while len(self._queries) > QUERY_CACHE_SIZE:
            self._queries.popitem(last=False)
        return vector

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return self._embed(texts) if texts else []


@dataclass(frozen=True)
class EmbeddingSettings:
    model: str


_cached: tuple[str, FastEmbedEmbedder] | None = None


def _settings() -> EmbeddingSettings | None:
    cfg = (get_app_config().get("retrieval") or {}).get("embedding") or {}
    override = get_settings().RETRIEVAL_EMBEDDING_ENABLED
    if not (cfg.get("enabled") if override is None else override):
        return None
    return EmbeddingSettings(model=str(cfg.get("model", bge_m3.DEFAULT)))


def get_configured_embedder() -> Embedder | None:
    """The embedder enabled in config, else None (BM25-only retrieval). A model that cannot load raises."""
    global _cached
    settings = _settings()
    if settings is None:
        return None
    if _cached is None or _cached[0] != settings.model:
        _cached = (settings.model, FastEmbedEmbedder(settings.model))
    return _cached[1]


def warm_up_embedder() -> bool:
    """Load the configured embedder now (startup) instead of on the first customer question.

    Returns whether one is enabled. A model that cannot load raises here, so a broken deployment fails at
    startup rather than silently serving weaker retrieval.
    """
    return get_configured_embedder() is not None


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return sum(x * y for x, y in zip(a, b, strict=False)) / (na * nb)

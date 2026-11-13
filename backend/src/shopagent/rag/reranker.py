"""Optional multilingual cross-encoder reranking for policy retrieval.

Measured on evals/retrieval/benchmark_v2.yaml (test split, 37 answerable queries) it lifts
Recall@1 from 0.57 to 0.95 at about 2 s per query on CPU, so it is opt-in via
config/app.yaml (`retrieval.reranker.enabled`). When enabled, a missing dependency or model is a
hard error: retrieval never silently falls back to the weaker ranking.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from shopagent.core.config import get_app_config, get_settings


class Reranker(Protocol):
    def scores(self, query: str, texts: Sequence[str]) -> list[float]: ...


class RerankerUnavailableError(RuntimeError):
    """Reranking is enabled but cannot run (dependency or model missing).

    Kept apart from PolicyIndexUnavailableError to avoid an import cycle; the search tool maps both
    to the same `index_unavailable` outcome.
    """


class CrossEncoderReranker:
    def __init__(self, model_name: str) -> None:
        try:
            from fastembed.rerank.cross_encoder import TextCrossEncoder  # type: ignore[import-not-found]

            self._model = TextCrossEncoder(model_name=model_name)
        except Exception as exc:  # ImportError, download or ONNX load failure
            raise RerankerUnavailableError(
                f"reranker '{model_name}' unavailable ({exc}); install the 'rerank' extra or disable "
                "retrieval.reranker.enabled"
            ) from exc

    def scores(self, query: str, texts: Sequence[str]) -> list[float]:
        return [float(x) for x in self._model.rerank(query, list(texts))]


_cached: tuple[str, Reranker] | None = None


@dataclass(frozen=True)
class RerankSettings:
    reranker: Reranker
    candidates: int
    # Best cross-encoder score below which the question is treated as outside the policy (None: never).
    min_score: float | None


def get_configured_reranker() -> RerankSettings | None:
    """The reranker and its settings when enabled in config, else None."""
    global _cached
    cfg = (get_app_config().get("retrieval") or {}).get("reranker") or {}
    override = get_settings().RETRIEVAL_RERANKER_ENABLED
    if not (cfg.get("enabled") if override is None else override):
        return None
    model = str(cfg["model"])
    if _cached is None or _cached[0] != model:
        _cached = (model, CrossEncoderReranker(model))
    min_score = cfg.get("min_score")
    return RerankSettings(
        reranker=_cached[1],
        candidates=int(cfg.get("candidates", 10)),
        min_score=None if min_score is None else float(min_score),
    )


def warm_up() -> bool:
    """Load the configured reranker now (startup) instead of on the first customer question.

    Returns whether a reranker is enabled. A model that cannot load raises here, so a broken deployment
    fails at startup rather than answering policy questions with silently weaker retrieval.
    """
    return get_configured_reranker() is not None

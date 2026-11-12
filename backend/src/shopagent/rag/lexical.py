"""Lexical ranking for policy retrieval: query normalisation and Okapi BM25.

Both are measured against the independent benchmark (evals/retrieval/benchmark_v2.yaml): BM25 with
normalisation beat the previous token-overlap + hashed n-gram fusion on Recall@1/4, MRR and nDCG
without a new dependency.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence

from shopagent.rag.chunker import tokenize_unaccent

# Informal chat spellings that customers use, mapped to the standard accent-stripped form of the
# index. Only general shorthand belongs here: never add a spelling just to fix one benchmark query.
CHAT_SHORTHAND = {
    "ko": "khong", "k": "khong", "hok": "khong", "hong": "khong", "khg": "khong", "kg": "khong",
    "dc": "duoc", "dk": "duoc", "sz": "size", "z": "vay", "v": "vay", "j": "gi",
    "mik": "minh", "mk": "minh", "ntn": "nhu the nao",
}

_THOUSAND_RE = re.compile(r"(\d+)\s*(?:k|nghìn|ngàn|nghin|ngan)\b")
_MILLION_RE = re.compile(r"(\d+)\s*(?:tr|triệu|trieu)\b")
_WORD_RE = re.compile(r"\w+")


def normalize_query(query: str) -> str:
    """Expand chat and money shorthand so '500k' and '500 nghìn' match the indexed '500000'."""
    text = query.lower()
    text = _THOUSAND_RE.sub(lambda m: str(int(m.group(1)) * 1000), text)
    text = _MILLION_RE.sub(lambda m: str(int(m.group(1)) * 1000000), text)
    return " ".join(CHAT_SHORTHAND.get(word, word) for word in _WORD_RE.findall(text))


class Bm25Index:
    """Okapi BM25 over accent-stripped tokens (k1=1.5, b=0.75)."""

    def __init__(self, documents: Sequence[str], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.docs = [tokenize_unaccent(d) for d in documents]
        self.avg_len = sum(len(d) for d in self.docs) / max(1, len(self.docs))
        doc_freq: dict[str, int] = {}
        for doc in self.docs:
            for term in set(doc):
                doc_freq[term] = doc_freq.get(term, 0) + 1
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in doc_freq.items()}

    def scores(self, query: str) -> list[float]:
        terms = tokenize_unaccent(query)
        out: list[float] = []
        for doc in self.docs:
            length = len(doc)
            total = 0.0
            for term in terms:
                tf = doc.count(term)
                if tf and term in self.idf:
                    total += self.idf[term] * tf * (self.k1 + 1) / (tf + self.k1 * (1 - self.b + self.b * length / self.avg_len))
            out.append(total)
        return out

    def max_possible(self, query: str) -> float:
        """Sum of idf over the query terms: the score a document matching every term would approach."""
        return sum(self.idf.get(t, 0.0) for t in set(tokenize_unaccent(query))) or 1.0

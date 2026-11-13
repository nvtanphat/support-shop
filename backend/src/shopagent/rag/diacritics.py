"""Restore Vietnamese diacritics in queries typed without them.

Customers often type "hang loi doi tra" with no accents. A multilingual cross-encoder scores such text
far lower than the same words with diacritics, which makes unsupported-query rejection unreliable
(reranker AUC 0.86 raw vs 0.985 restored on the independent query set). Restoration is a dictionary lookup built
from the policy text itself plus a short list of very common function words, so it needs no model.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Callable, Iterable

from shopagent.rag.chunker import remove_vietnamese_accents

# Function words of everyday Vietnamese whose accented form the policy text may not show (or may show
# in a rarer sense, e.g. "tối" for "toi"). General vocabulary only, never tuned to a benchmark query.
FUNCTION_WORDS = ["tôi", "mình", "không", "được", "có", "bao", "nhiêu", "mất", "mấy", "ngày", "hàng", "tiền", "về", "vì", "thì", "là", "gì", "nào", "chịu", "hỏi", "nữa", "còn", "cho", "của", "và", "hay", "hoặc", "với", "khi", "nếu", "đã", "sẽ", "đang", "rồi", "này", "kia", "đó", "cần", "muốn", "biết", "giúp", "xin", "làm", "thế", "nào", "sao", "ở", "đâu", "lâu", "nhanh", "ai", "bị", "phải", "trong", "sau", "trước", "tại", "các", "những", "một", "hai", "ba", "bốn", "năm"]

_WORD = re.compile(r"\w+")


def _has_diacritics(text: str) -> bool:
    return any(unicodedata.combining(ch) or ch in "đĐ" for ch in unicodedata.normalize("NFD", text))


def build_restorer(corpus_texts: Iterable[str]) -> Callable[[str], str]:
    """A function that adds diacritics to an unaccented query; accented text is returned unchanged."""
    counts = Counter(w for text in corpus_texts for w in _WORD.findall(text.lower()))
    best: dict[str, str] = {}
    for word, n in counts.items():
        key = remove_vietnamese_accents(word)
        if key not in best or n > counts[best[key]]:
            best[key] = word
    for word in FUNCTION_WORDS:
        best[remove_vietnamese_accents(word)] = word  # common words win over corpus frequency

    def restore(query: str) -> str:
        if _has_diacritics(query):
            return query
        return " ".join(best.get(token, token) for token in _WORD.findall(query.lower()))

    return restore

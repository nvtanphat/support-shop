"""Policy documents written as Markdown files, and the checks every clause must pass before it is indexed.

The generated clauses (rag/generator.py) cover rules that carry numbers and come from config/policy/rules.yaml.
Everything else (FAQ, warranty, how-to text) is a Markdown file under config/policy/docs/ with a YAML header:

    ---
    clause_id: POL-WARRANTY-01
    topic: warranty
    title: Bảo hành điện tử
    version: "2026-11-01"           # optional, defaults to the rules.yaml version
    effective_from: 2026-11-01      # optional, defaults to the rules.yaml date
    effective_to: null              # optional
    category_scope: [electronics_accessories]   # optional, defaults to [all]
    parent_id: POL-WARRANTY-00      # optional: the clause this one was cut from
    status: active                  # active (default) | retired
    ---
    Body text, one clause per file.

validate_clauses() runs on generated and document clauses together, so a document cannot silently shadow or
contradict a generated one.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from itertools import pairwise
from pathlib import Path
from typing import Any

import yaml

from shopagent.core.config import CONFIG_DIR

DOCS_DIR = CONFIG_DIR / "policy" / "docs"
# One clause is returned to the model whole, so its size is bounded here rather than truncated later.
MAX_CLAUSE_CHARS = 1200
CLAUSE_ID_RE = re.compile(r"^POL-[A-Z]+-\d{2}$")
_CLAUSE_MENTION_RE = re.compile(r"POL-[A-Z]+-\d{2}(?!\d)")
_FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", re.DOTALL)
STATUSES = frozenset({"active", "retired"})


class PolicyDocumentError(ValueError):
    """The policy corpus is inconsistent; the message lists every problem found."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("policy corpus is invalid:\n- " + "\n- ".join(problems))


def _iso(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day).isoformat()
    return str(value)


def parse_document(path: Path, rules: dict[str, Any]) -> dict[str, Any]:
    """One clause from one Markdown file."""
    raw = path.read_text(encoding="utf-8")
    match = _FRONT_MATTER_RE.match(raw.replace("\r\n", "\n"))
    if match is None:
        raise PolicyDocumentError([f"{path.name}: missing the '---' YAML header"])
    try:
        meta = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        raise PolicyDocumentError([f"{path.name}: header is not valid YAML ({exc})"]) from exc
    if not isinstance(meta, dict):
        raise PolicyDocumentError([f"{path.name}: header must be a mapping"])
    return {
        "clause_id": str(meta.get("clause_id", "")),
        "topic": str(meta.get("topic", "")),
        "title": meta.get("title"),
        "category_scope": list(meta.get("category_scope") or ["all"]),
        "version": str(meta.get("version") or rules.get("version", "2026-11-01")),
        "effective_from": _iso(meta.get("effective_from")) or rules.get("effective_from"),
        "effective_to": _iso(meta.get("effective_to")),
        "parent_id": meta.get("parent_id"),
        "status": str(meta.get("status") or "active"),
        "text": match.group(2).strip(),
        "source": f"policy/docs/{path.name}",
    }


def load_documents(rules: dict[str, Any], docs_dir: Path | None = None) -> list[dict[str, Any]]:
    """Every clause under the documents directory (none when the directory does not exist)."""
    directory = docs_dir if docs_dir is not None else DOCS_DIR
    if not directory.exists():
        return []
    problems: list[str] = []
    clauses: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.md")):
        try:
            clauses.append(parse_document(path, rules))
        except PolicyDocumentError as exc:
            problems.extend(exc.problems)
    if problems:
        raise PolicyDocumentError(problems)
    return clauses


def _as_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    dt = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    return dt.replace(tzinfo=None) if dt.tzinfo else dt  # compare wall clock; the corpus uses one timezone


def validate_clauses(clauses: list[dict[str, Any]]) -> None:
    """Raise PolicyDocumentError listing every inconsistency in the corpus."""
    problems: list[str] = []
    known = {c["clause_id"] for c in clauses}
    seen: set[tuple[str, str]] = set()
    spans: dict[str, list[tuple[datetime, datetime | None, str, str]]] = {}

    for c in clauses:
        cid, where = c["clause_id"], c.get("source", "rules.yaml")
        label = f"{cid} ({where})"
        if not CLAUSE_ID_RE.match(cid):
            problems.append(f"{label}: clause_id must look like POL-TOPIC-01")
        if not c.get("topic"):
            problems.append(f"{label}: topic is empty")
        text = c.get("text", "")
        if not text.strip():
            problems.append(f"{label}: text is empty")
        elif len(text) > MAX_CLAUSE_CHARS:
            problems.append(f"{label}: text has {len(text)} characters, the limit is {MAX_CLAUSE_CHARS}; cut it into several clauses with parent_id")
        if c.get("status", "active") not in STATUSES:
            problems.append(f"{label}: status must be one of {sorted(STATUSES)}")
        key = (cid, str(c.get("version")))
        if key in seen:
            problems.append(f"{label}: clause_id {cid} version {key[1]} is defined more than once")
        seen.add(key)
        start, end = _as_dt(c.get("effective_from")), _as_dt(c.get("effective_to"))
        if start is not None and end is not None and end <= start:
            problems.append(f"{label}: effective_to is not after effective_from")
        if start is not None and c.get("status", "active") == "active":
            spans.setdefault(cid, []).append((start, end, key[1], where))
        for mentioned in sorted(set(_CLAUSE_MENTION_RE.findall(text)) - known):
            problems.append(f"{label}: refers to {mentioned}, which does not exist")
        parent = c.get("parent_id")
        if parent and parent not in known:
            problems.append(f"{label}: parent_id {parent} does not exist")
        if parent and parent == cid:
            problems.append(f"{label}: parent_id points to itself")

    for cid, items in spans.items():
        items.sort(key=lambda s: s[0])
        for (_s1, e1, v1, w1), (s2, _e2, v2, w2) in pairwise(items):
            if e1 is None or s2 < e1:
                problems.append(f"{cid}: versions {v1} ({w1}) and {v2} ({w2}) are in force at the same time")

    if problems:
        raise PolicyDocumentError(problems)

"""Policy indexer: keeps the policy_chunks table in step with the corpus without rewriting what did not change.

The corpus is the generated clauses (config/policy/rules.yaml) plus the Markdown documents under
config/policy/docs/. sync_policies() validates the whole corpus first, then for each (clause_id, version):

- not in the table            -> added (and embedded)
- in the table, hash differs  -> updated (and re-embedded)
- in the table, hash equal    -> left alone
- in the table, not in corpus -> retired (status="retired", never deleted, so history stays auditable)

Only changed chunks are embedded, so growing the corpus does not make every re-index slower.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shopagent.core.clock import get_clock, get_shop_timezone
from shopagent.core.config import get_rules_config
from shopagent.infra.db.tables import PolicyChunkModel, PolicyDocumentModel
from shopagent.rag.chunker import build_chunks_from_clauses
from shopagent.rag.documents import load_documents, validate_clauses
from shopagent.rag.embeddings import get_embedding_provider
from shopagent.rag.generator import generate_policy_clauses

_DEFAULT_FROM = "2026-11-01T00:00:00+07:00"


@dataclass
class IndexReport:
    added: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    retired: list[str] = field(default_factory=list)
    active: list[dict[str, Any]] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"{len(self.active)} điều khoản đang hiệu lực: thêm {len(self.added)}, "
            f"cập nhật {len(self.updated)}, giữ nguyên {len(self.unchanged)}, ngừng dùng {len(self.retired)}"
        )


def _key(clause_id: str, version: str) -> str:
    return f"{clause_id}@{version}"


def _when(value: str | None, default: str | None = None) -> datetime | None:
    raw = value or default
    if raw is None:
        return None
    parsed = datetime.fromisoformat(raw)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=get_shop_timezone())


def build_corpus(rules: dict[str, Any] | None = None, docs_dir: Path | None = None) -> list[dict[str, Any]]:
    """Generated clauses plus documents, validated together. Raises PolicyDocumentError when inconsistent."""
    rules_cfg = rules if rules is not None else get_rules_config()
    clauses = generate_policy_clauses(rules_cfg) + load_documents(rules_cfg, docs_dir)
    validate_clauses(clauses)
    return clauses


async def _document_for(session: AsyncSession, version: str, effective_from: datetime) -> PolicyDocumentModel:
    slug = f"shoplab-policy-{version}"
    doc = (await session.execute(select(PolicyDocumentModel).where(PolicyDocumentModel.slug == slug))).scalar_one_or_none()
    if doc is None:
        doc = PolicyDocumentModel(
            id=uuid.uuid4(),
            title=f"Chính sách bán hàng và đổi trả ShopLab {version}",
            slug=slug,
            version=version,
            effective_from=effective_from,
        )
        session.add(doc)
        await session.flush()
    return doc


async def sync_policies(
    session: AsyncSession, rules: dict[str, Any] | None = None, docs_dir: Path | None = None
) -> IndexReport:
    """Bring policy_chunks in line with the corpus and report what changed."""
    chunks = build_corpus(rules, docs_dir)
    chunks = build_chunks_from_clauses(chunks)
    wanted = {_key(c["clause_id"], str(c["version"])): c for c in chunks}

    existing = {
        _key(row.clause_id, row.version): row for row in (await session.execute(select(PolicyChunkModel))).scalars().all()
    }
    report = IndexReport()
    embedder = get_embedding_provider()

    to_write = [
        key for key, c in wanted.items()
        if key not in existing or existing[key].content_hash != c["content_hash"] or existing[key].status != c["status"]
    ]
    vectors = dict(zip(to_write, embedder.embed_documents([wanted[k]["text"] for k in to_write]), strict=True))
    now = get_clock().now()

    for key, c in wanted.items():
        row = existing.get(key)
        start = _when(c.get("effective_from"), _DEFAULT_FROM)
        assert start is not None
        if row is not None and key not in vectors:
            report.unchanged.append(key)
        else:
            fields = {
                "topic": c["topic"],
                "category_scope": c["category_scope"],
                "effective_from": start,
                "effective_to": _when(c.get("effective_to")),
                "text": c["text"],
                "text_unaccent": c["text_unaccent"],
                "embedding": vectors[key],
                "source": c["source"],
                "title": c.get("title"),
                "parent_id": c.get("parent_id"),
                "status": c["status"],
                "content_hash": c["content_hash"],
                "updated_at": now,
            }
            if row is None:
                doc = await _document_for(session, str(c["version"]), start)
                session.add(
                    PolicyChunkModel(
                        id=c["id"], document_id=doc.id, clause_id=c["clause_id"], version=str(c["version"]), **fields
                    )
                )
                report.added.append(key)
            else:
                for name, value in fields.items():
                    setattr(row, name, value)
                report.updated.append(key)
        if c["status"] == "active":
            report.active.append({"clause_id": c["clause_id"], "topic": c["topic"], "text": c["text"], "text_unaccent": c["text_unaccent"]})

    for key, row in existing.items():
        if key not in wanted and row.status != "retired":
            row.status = "retired"
            row.updated_at = now
            report.retired.append(key)

    await session.commit()
    return report


async def index_policies(session: AsyncSession, rules: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Index the corpus and return the clauses now in force (kept for callers that only need the list)."""
    return (await sync_policies(session, rules)).active


if __name__ == "__main__":
    # Same entry point the README documents; the click command `shopagent index-policies` is equivalent.
    from shopagent.cli import index_policies_cmd

    index_policies_cmd()

"""Policy indexer persisting chunks into database."""

from __future__ import annotations

from datetime import datetime
from typing import Any
import uuid
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from shopagent.infra.db.tables import PolicyChunkModel, PolicyDocumentModel
from shopagent.rag.chunker import build_chunks_from_clauses
from shopagent.rag.embeddings import get_embedding_provider
from shopagent.rag.generator import generate_policy_clauses


async def index_policies(session: AsyncSession, rules: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Generate, embed, and index policy clauses into DB tables."""
    clauses = generate_policy_clauses(rules)
    chunks = build_chunks_from_clauses(clauses)
    embedder = get_embedding_provider()

    version = chunks[0]["version"] if chunks else "2026-11-01"

    # 1. Ensure Policy Document
    doc_slug = f"shoplab-policy-{version}"
    stmt_doc = select(PolicyDocumentModel).where(PolicyDocumentModel.slug == doc_slug)
    res_doc = await session.execute(stmt_doc)
    doc = res_doc.scalar_one_or_none()
    if not doc:
        doc = PolicyDocumentModel(
            id=uuid.uuid4(),
            title=f"Chính sách bán hàng và đổi trả ShopLab {version}",
            slug=doc_slug,
            version=version,
            effective_from=datetime.fromisoformat("2026-11-01T00:00:00+07:00"),
        )
        session.add(doc)
        await session.flush()

    # 2. Clear previous chunks for this document
    stmt_del = delete(PolicyChunkModel).where(PolicyChunkModel.document_id == doc.id)
    await session.execute(stmt_del)

    # 3. Insert embedded chunks
    texts = [c["text"] for c in chunks]
    embeddings = embedder.embed_documents(texts)

    saved_chunks = []
    for c, emb in zip(chunks, embeddings):
        chunk_model = PolicyChunkModel(
            id=c["id"],
            document_id=doc.id,
            clause_id=c["clause_id"],
            topic=c["topic"],
            category_scope=c["category_scope"],
            version=c["version"],
            effective_from=datetime.fromisoformat(c["effective_from"]) if c.get("effective_from") else datetime.fromisoformat("2026-11-01T00:00:00+07:00"),
            effective_to=datetime.fromisoformat(c["effective_to"]) if c.get("effective_to") else None,
            text=c["text"],
            text_unaccent=c["text_unaccent"],
            embedding=emb,
        )
        session.add(chunk_model)
        saved_chunks.append({
            "clause_id": c["clause_id"],
            "topic": c["topic"],
            "text": c["text"],
            "text_unaccent": c["text_unaccent"],
            "embedding": emb,
        })

    await session.commit()
    return saved_chunks

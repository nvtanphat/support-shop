"""Public read-only policy endpoints: the clauses the agent cites, in force right now."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shopagent.api.deps import get_db_session
from shopagent.core.clock import get_clock
from shopagent.infra.db.tables import PolicyChunkModel

router = APIRouter(prefix="/policies", tags=["Policies"])

_FIRST_SENTENCE = re.compile(r"^(.+?[.!?])(?:\s|$)", re.DOTALL)


def _title(text: str) -> str:
    """The clause title is its first sentence, so the list needs no separately maintained label."""
    match = _FIRST_SENTENCE.match(text)
    return (match.group(1) if match else text).rstrip(".")


def _naive_utc(moment: datetime) -> datetime:
    """SQLite hands back naive timestamps; treat them as UTC so both backends compare the same way."""
    if moment.tzinfo is None:
        return moment
    return moment.astimezone(UTC).replace(tzinfo=None)


async def _in_force(session: AsyncSession) -> list[PolicyChunkModel]:
    now = _naive_utc(get_clock().now())
    rows = (await session.execute(select(PolicyChunkModel).order_by(PolicyChunkModel.clause_id))).scalars().all()
    return [
        r
        for r in rows
        if _naive_utc(r.effective_from) <= now and (r.effective_to is None or now < _naive_utc(r.effective_to))
    ]


def _summary(row: PolicyChunkModel) -> dict[str, Any]:
    return {
        "clause_id": row.clause_id,
        "topic": row.topic,
        "title": _title(row.text),
        "version": row.version,
        "effective_from": row.effective_from.isoformat(),
        "effective_to": row.effective_to.isoformat() if row.effective_to else None,
    }


@router.get("")
async def list_policies(session: AsyncSession = Depends(get_db_session)) -> dict[str, Any]:
    """Clauses currently in force, newest version per clause id."""
    rows = await _in_force(session)
    return {"policies": [_summary(r) for r in rows]}


@router.get("/{clause_id}")
async def get_policy(clause_id: str, session: AsyncSession = Depends(get_db_session)) -> dict[str, Any]:
    rows = [r for r in await _in_force(session) if r.clause_id == clause_id.upper()]
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Không tìm thấy điều khoản đang có hiệu lực với mã này.")
    return {**_summary(rows[0]), "text": rows[0].text}

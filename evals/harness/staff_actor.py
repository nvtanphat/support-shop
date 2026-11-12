"""Staff workflow simulator for evaluation harness."""

from __future__ import annotations

import uuid

from shopagent.core.principal import Principal, PrincipalRole
from shopagent.domain.models.enums import ApprovalStatus
from shopagent.domain.services.approvals import ApprovalService
from shopagent.infra.db.tables import ApprovalRequestModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from evals.harness.models import StaffAction


class StaffActor:
    """Executes staff actions configured in evaluation scenarios."""

    def __init__(self, actions: list[StaffAction]) -> None:
        self.actions = actions
        self._executed: set[int] = set()

    async def step(self, session: AsyncSession) -> list[str]:
        """Check for pending approval requests and apply matching staff decisions."""
        if not self.actions:
            return []

        approval_service = ApprovalService(session)

        # Get pending approvals
        stmt = select(ApprovalRequestModel).where(
            ApprovalRequestModel.status == ApprovalStatus.PENDING.value
        )
        res = await session.execute(stmt)
        pending_list = res.scalars().all()

        results: list[str] = []

        for p in pending_list:
            for idx, act in enumerate(self.actions):
                if idx in self._executed:
                    continue
                if p.gate == act.gate or act.gate in ("*", "any"):
                    role = PrincipalRole(act.role)
                    staff_principal = Principal.staff(
                        user_id=uuid.UUID(int=1 if act.role == "agent" else 2),
                        role=role,
                    )
                    decision = (
                        ApprovalStatus.APPROVED
                        if act.decision == "approve"
                        else ApprovalStatus.REJECTED
                    )
                    await approval_service.decide_approval(
                        approval_id=p.id,
                        decision=decision,
                        principal=staff_principal,
                        note=act.note or "Eval simulated staff decision",
                    )
                    self._executed.add(idx)
                    results.append(
                        f"Staff ({act.role}) {act.decision} approval {p.id} for gate {p.gate}"
                    )
                    break

        return results

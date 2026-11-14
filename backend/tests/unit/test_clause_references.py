"""Every clause id the code can hand to a customer exists in the policy index.

A clause the engine returns but the index does not contain cannot be looked up by the agent, so
the output verifier blocks the reply that cites it.
"""

from __future__ import annotations

import re
from pathlib import Path

from shopagent.rag.generator import generate_policy_clauses

_CLAUSE_RE = re.compile(r'"(POL-[A-Z]+-\d{2})"')
_SOURCES = ["backend/src/shopagent/domain", "backend/src/shopagent/agent"]


def test_clause_ids_used_in_code_exist_in_the_policy_index() -> None:
    indexed = {c["clause_id"] for c in generate_policy_clauses()}
    used: dict[str, str] = {}
    for root in _SOURCES:
        for path in Path(root).rglob("*.py"):
            for clause in _CLAUSE_RE.findall(path.read_text(encoding="utf-8")):
                used.setdefault(clause, str(path))
    missing = {c: where for c, where in used.items() if c not in indexed}
    assert not missing, f"Clause ids referenced in code but absent from the policy index: {missing}"


def test_ground_truth_and_scenarios_cite_indexed_clauses() -> None:
    indexed = {c["clause_id"] for c in generate_policy_clauses()}
    for path in [Path("evals/ground_truth/policy_decision_table.csv"), *Path("evals").glob("scenarios*/*.yaml")]:
        for clause in re.findall(r"POL-[A-Z]+-\d{2}(?!\d)", path.read_text(encoding="utf-8")):
            assert clause in indexed, f"{path} cites {clause}, which is not in the policy index"

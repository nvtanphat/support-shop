"""Test evaluation independence.

Section 7.1 & 14.3:
The evaluation harness, ground truth, and scenarios MUST NOT read or reference `rules.yaml`.
This test scans the evals/ directory and fails if any file references rules.yaml.
"""

from __future__ import annotations

from pathlib import Path


def test_evals_do_not_reference_rules_yaml() -> None:
    evals_dir = Path("evals")
    assert evals_dir.exists(), "evals directory must exist"

    violations: list[str] = []

    for file_path in evals_dir.rglob("*"):
        if file_path.is_file() and file_path.suffix in (".py", ".yaml", ".yml", ".json", ".csv", ".md"):
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            if "rules.yaml" in content:
                violations.append(str(file_path))

    assert not violations, (
        f"Violation of Eval Independence: files in evals/ reference 'rules.yaml': {violations}"
    )

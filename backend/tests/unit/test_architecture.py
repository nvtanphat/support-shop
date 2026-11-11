"""Architecture boundaries test ensuring domain clean architecture."""

from __future__ import annotations

import importlib
import inspect
import os
from pathlib import Path
import sys


def test_domain_layer_has_no_framework_dependencies() -> None:
    """AGENTS.md Section 5: domain/ is the single source of truth for business rules;

    must NOT depend on FastAPI, LangGraph, LLM SDK, or frontend.
    """
    domain_dir = Path(__file__).resolve().parent.parent.parent / "src" / "shopagent" / "domain"
    forbidden_modules = [
        "fastapi",
        "starlette",
        "langgraph",
        "langchain",
        "google.genai",
        "google",
        "httpx",
    ]

    violations: list[str] = []

    for py_file in domain_dir.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        rel_path = py_file.relative_to(domain_dir)
        content = py_file.read_text(encoding="utf-8")

        for line_num, line in enumerate(content.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                for forbidden in forbidden_modules:
                    if f"import {forbidden}" in stripped or f"from {forbidden}" in stripped:
                        violations.append(f"{rel_path}:{line_num} -> {stripped}")

    assert not violations, f"Architecture violation: domain/ must not import external frameworks:\n" + "\n".join(violations)

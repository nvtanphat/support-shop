"""Parse scenario YAML files into validated Scenario objects."""

from __future__ import annotations

from pathlib import Path

import yaml

from evals.harness.models import (
    SUPPORTED_DB_TABLES,
    SUPPORTED_EXPECT_KEYS,
    SUPPORTED_FORBIDDEN_KINDS,
    SUPPORTED_REQUIRED_FACT_KINDS,
    ForbiddenPattern,
    RequiredFact,
    Scenario,
    ScenarioExpectation,
    ScriptStep,
    StaffAction,
    UserScript,
)


def load_scenario_from_yaml(path: Path) -> Scenario:
    """Parse scenario definition from YAML file."""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    user_data = data.get("user", {})
    script_steps = [
        ScriptStep(
            say=st.get("say", ""),
            when_asked=st.get("when_asked"),
            on_proposal=st.get("on_proposal"),
            do=st.get("do"),
        )
        for st in user_data.get("script", [])
    ]
    user_script = UserScript(
        goal=user_data.get("goal", ""),
        script=script_steps,
        fallback_say=user_data.get("fallback_say", "Bạn cần mình cung cấp thông tin gì?"),
        max_turns=user_data.get("max_turns", 10),
    )

    staff_actions = [
        StaffAction(
            when_event=sa.get("when_event", "approval.created"),
            gate=sa.get("gate", "*"),
            decision=sa.get("decision", "approve"),
            role=sa.get("role", "agent"),
            note=sa.get("note", ""),
        )
        for sa in data.get("staff", [])
    ]

    expect_data = data.get("expect", {})
    req_facts = [
        RequiredFact(
            kind=rf.get("kind", ""),
            value=rf.get("value"),
            id=rf.get("id"),
            note=rf.get("note", ""),
        )
        for rf in expect_data.get("required_facts", [])
    ]
    forbidden_patterns = [
        ForbiddenPattern(
            kind=fp.get("kind", "claim"),
            pattern=fp.get("pattern", ""),
        )
        for fp in expect_data.get("forbidden", [])
    ]

    ordering_raw = expect_data.get("tool_ordering", [])
    tool_ordering = [
        (item[0], item[1]) if isinstance(item, (list, tuple)) and len(item) == 2 else (item.get("first"), item.get("second"))
        for item in ordering_raw
    ]

    unknown_keys = set(expect_data) - SUPPORTED_EXPECT_KEYS
    unknown_tables = set(expect_data.get("db", {})) - SUPPORTED_DB_TABLES
    unknown_facts = {rf.kind for rf in req_facts} - SUPPORTED_REQUIRED_FACT_KINDS
    unknown_forbidden = {fp.kind for fp in forbidden_patterns} - SUPPORTED_FORBIDDEN_KINDS
    problems = [
        f"{label}: {sorted(bad)}"
        for label, bad in (
            ("unknown expect keys", unknown_keys),
            ("unknown db tables", unknown_tables),
            ("unknown required_fact kinds", unknown_facts),
            ("unknown forbidden kinds", unknown_forbidden),
        )
        if bad
    ]
    if problems:
        raise ValueError(f"Scenario {data.get('id', path.name)} has unsupported assertions: {'; '.join(problems)}")

    expect = ScenarioExpectation(
        db=expect_data.get("db", {}),
        required_facts=req_facts,
        forbidden=forbidden_patterns,
        max_tool_calls=expect_data.get("max_tool_calls", 10),
        required_tools=expect_data.get("required_tools", []),
        required_tool_args=expect_data.get("required_tool_args", {}),
        tool_ordering=tool_ordering,
    )

    return Scenario(
        id=data["id"],
        group=data.get("group", ""),
        tags=data.get("tags", []),
        clock=data.get("clock", "2026-11-11T10:00:00+07:00"),
        principal=data.get("principal", {}),
        fixtures=data.get("fixtures", {}),
        user=user_script,
        staff=staff_actions,
        expect=expect,
    )

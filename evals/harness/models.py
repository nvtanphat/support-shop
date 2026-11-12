"""Evaluation Scenario and Metric Data Models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ScenarioFixtureItem:
    key: str
    sku: str
    qty: int
    unit_price: int
    product_name: str = ""
    flags: list[str] = field(default_factory=list)


@dataclass
class ScenarioFixtureOrder:
    code: str
    status: str
    delivered_at: str | None = None  # relative string like "-6d" or ISO
    placed_at: str | None = None
    payment_method: str = "card"
    subtotal: int = 0
    discount_total: int = 0
    shipping_fee: int = 0
    items: list[ScenarioFixtureItem] = field(default_factory=list)


@dataclass
class ScriptStep:
    say: str = ""
    when_asked: str | None = None  # reason, condition, order_code, etc.
    on_proposal: dict[str, Any] | None = None  # {type: return, expect_items: [...]}
    do: str | None = None  # confirm | cancel


@dataclass
class UserScript:
    goal: str
    script: list[ScriptStep] = field(default_factory=list)
    fallback_say: str = "Bạn cần mình cung cấp thêm thông tin gì?"
    max_turns: int = 10


@dataclass
class StaffAction:
    when_event: str
    gate: str
    decision: str  # approve | reject
    role: str = "agent"  # agent | supervisor
    note: str = ""


@dataclass
class RequiredFact:
    kind: str  # amount_vnd | clause | status
    value: Any = None
    id: str | None = None
    note: str = ""


@dataclass
class ForbiddenPattern:
    kind: str  # claim | pattern | tool
    pattern: str = ""


@dataclass
class ScenarioExpectation:
    db: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    required_facts: list[RequiredFact] = field(default_factory=list)
    forbidden: list[ForbiddenPattern] = field(default_factory=list)
    max_tool_calls: int = 10


@dataclass
class Scenario:
    id: str
    group: str
    tags: list[str] = field(default_factory=list)
    clock: str = "2026-11-11T10:00:00+07:00"
    principal: dict[str, Any] = field(default_factory=lambda: {"type": "customer", "email": "customer@example.com"})
    fixtures: dict[str, Any] = field(default_factory=dict)
    user: UserScript = field(default_factory=lambda: UserScript(goal=""))
    staff: list[StaffAction] = field(default_factory=list)
    expect: ScenarioExpectation = field(default_factory=ScenarioExpectation)


@dataclass
class ScenarioRunResult:
    scenario_id: str
    passed: bool
    db_passed: bool
    facts_passed: bool
    forbidden_passed: bool
    invariants_passed: bool
    tool_calls_count: int
    turns_count: int
    fallback_turns: int
    errors: list[str] = field(default_factory=list)
    safety_violations: list[str] = field(default_factory=list)
    dialogue: list[dict[str, Any]] = field(default_factory=list)

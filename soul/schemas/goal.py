"""Goal — 目标生命周期。source ∈ {user, self, long_term, ...}。"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Goal:
    goal_id: str
    title: str = ""
    source: str = ""
    priority: int = 0                      # 数值越大越优先
    status: str = "active"                 # active / suspended / completed / cancelled
    reason: str = ""
    related_beliefs: list[str] = field(default_factory=list)
    related_relationships: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
"""Relationship — 对象关系模型，变化必须可追溯（Constitution 02）。"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Relationship:
    person_id: str
    name: str = ""
    trust: float = 0.0
    familiarity: float = 0.0
    importance: float = 0.0
    affinity: float = 0.0
    shared_goals: list[str] = field(default_factory=list)
    conflict_history: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    last_interaction_at: str = ""
    version: int = 1
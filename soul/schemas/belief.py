"""Belief — 必须关联 evidence（Constitution 02）。"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Belief:
    belief_id: str
    statement: str
    confidence: float = 0.0
    evidence_ids: list[str] = field(default_factory=list)
    supporting_episode_ids: list[str] = field(default_factory=list)
    contradiction_ids: list[str] = field(default_factory=list)
    version: int = 1
    created_at: str = ""
    updated_at: str = ""
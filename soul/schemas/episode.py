"""Episode — 由多个 event 组成的经历片段。"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Episode:
    episode_id: str
    start_time: str
    end_time: str
    summary: str = ""
    event_ids: list[str] = field(default_factory=list)
    actors: list[str] = field(default_factory=list)
    outcome: Optional[str] = None
    importance_score: float = 0.0
    emotional_trace: dict[str, float] = field(default_factory=dict)  # 8 维情绪
    tags: list[str] = field(default_factory=list)
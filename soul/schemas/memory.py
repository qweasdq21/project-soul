"""Memory — 分层保存。memory_type ∈ {working, episode, semantic, relationship, core, archive}。"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Memory:
    memory_id: str
    memory_type: str
    content: str
    source_episode_ids: list[str] = field(default_factory=list)
    confidence: float = 0.0
    importance: float = 0.0
    retrieval_weight: float = 0.0
    decay_score: float = 0.0
    created_at: str = ""
    updated_at: str = ""
    archived: bool = False
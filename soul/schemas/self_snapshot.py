"""Self Snapshot — 计算得到的当前自我状态（不是 prompt 人设）。"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class SelfSnapshot:
    snapshot_id: str
    timestamp: str
    identity_summary: str = ""
    active_beliefs: list[str] = field(default_factory=list)       # belief_id 列表
    active_relationships: list[str] = field(default_factory=list)  # person_id 列表
    active_goals: list[str] = field(default_factory=list)          # goal_id 列表
    dominant_narratives: list[str] = field(default_factory=list)   # narrative_id 列表
    current_emotion_state: dict[str, float] = field(default_factory=dict)  # 8 维情绪
    change_log: list[dict] = field(default_factory=list)           # 相对上一快照的变更说明
    evidence_refs: list[str] = field(default_factory=list)
    version: int = 1
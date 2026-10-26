"""Narrative — 解释 evidence 的意义；必须引用 evidence/episode，旧版本归档（supersedes）。"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Narrative:
    narrative_id: str
    title: str = ""
    narrative_type: str = ""
    content: str = ""
    meaning: str = ""
    identity_effect: str = ""
    evidence_ids: list[str] = field(default_factory=list)
    episode_ids: list[str] = field(default_factory=list)
    version: int = 1
    supersedes: Optional[str] = None  # 被替代的旧版本 ID，或 None(新叙事)
    created_at: str = ""
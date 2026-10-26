"""Fast Loop — Realtime Cognitive Loop（实时、低延迟）。

流程：Perception → Emotion → Importance → Working Memory →
      Decision → Action → Short Reflection → Episode Queue
Phase 1 仅循环骨架（空）。
"""
from __future__ import annotations


class FastLoop:
    """实时认知循环。Phase 2+ 实现完整流程。"""

    def __init__(self) -> None:
        pass

    def step(self, user_input: object) -> object:
        raise NotImplementedError  # Phase 2+ 实现
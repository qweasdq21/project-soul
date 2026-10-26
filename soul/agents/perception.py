"""Perception Agent — 把输入消息转成结构化 Event。

Constitution: 只负责归一化事实，不做解释、评价或情绪判断。
Phase 2 实现：规则式归一化 + Event 对象构造。
"""
from __future__ import annotations
import uuid
from dataclasses import asdict
from datetime import datetime, timezone

from soul.agents.base import BaseAgent
from soul.schemas.events import Event


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class PerceptionAgent(BaseAgent):
    """输入: raw user message（+ 可选 metadata dict）
    输出: Event 对象（含 event_id/timestamp/source/actor/event_type/
          raw_content/normalized_content/metadata/hash(空)/previous_hash(空)/created_at）
    """
    name = "perception"

    def process(
        self,
        raw: str,
        metadata: dict | None = None,
        *,
        actor: str = "user",
        event_type: str = "user_message",
        source: str = "cli",
    ) -> Event:
        if not isinstance(raw, str):
            raise TypeError("PerceptionAgent.process requires a str message")
        normalized = raw.strip()
        now = _utc_now()
        return Event(
            event_id=str(uuid.uuid4()),
            timestamp=now,
            source=source,
            actor=actor,
            event_type=event_type,
            raw_content=raw,
            normalized_content=normalized,
            metadata=metadata or {},
            hash="",
            previous_hash=None,
            created_at=now,
        )


def event_to_dict(event: Event) -> dict:
    """把 Event dataclass 转成 dict（供 EvidenceStore 计算 hash 用）。"""
    return asdict(event)
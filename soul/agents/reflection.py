"""Reflection Agent — 反思。Phase 3：Short Reflection。

Short Reflection：对重要 episode 生成短反思，必须引用 episode_id / event_id。
输出 reflection 条目（落库）。
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone

from soul.agents.base import BaseAgent


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class ReflectionAgent(BaseAgent):
    """输入: 一个 episode（dict，含 event_ids / summary 等）
    输出: Reflection dict {reflection_id, episode_id, event_id, content, created_at}
    短反思只对 episode_candidate 触发。内容必须源自 episode 的 evidence（不凭空）。
    """
    name = "reflection"
    export_format = "dict"

    def process(self, episode: dict) -> dict:
        # SQLite read() 返回的 dict 键是 event_ids_json（JSON 字符串），
        # 原始 episode dict 才是 event_ids（list）。两者都要兼容。
        import json as _json
        ids_raw = episode.get("event_ids")
        if ids_raw is None:
            ids_raw = _json.loads(episode.get("event_ids_json", "[]"))
        elif not isinstance(ids_raw, list):
            ids_raw = _json.loads(ids_raw)
        event_ids = list(ids_raw)
        eid = episode.get("episode_id", "")
        event_id = event_ids[0] if event_ids else episode.get("event_id")
        summary = episode.get("summary", "")
        importance = episode.get("importance_score", 0.0)

        content = (
            f"Episode 反思: “{summary[:120]}” "
            f"(importance={importance:.2f}) "
            f"触发了短反思，源于 {len(event_ids)} 条 evidence 事件。"
        )
        return {
            "reflection_id": f"ref-{uuid.uuid4()}",
            "episode_id": eid,
            "event_id": event_id,
            "content": content,
            "created_at": _utc_now(),
        }
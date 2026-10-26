"""Memory Agent — 管理多层记忆落库。Phase 3：Working + Episode Memory。

Memory 不能脱离 evidence：每条 memory 必须引用 event_id（Constitution 02）。
MVP 只做 working + episode 写入，不做 Semantic / Core / Archive 复杂逻辑。
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone

from soul.agents.base import BaseAgent


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class MemoryAgent(BaseAgent):
    """输入: (event_dict, importance_result, appraisal_dict, sqlite_store)
    输出: dict {working_memory_id?, episode_id?, written_layers: [...]}
    根据 target_memory_layer:
      - working → 写 working_memory
      - episode_candidate → 写 working_memory + 生成 episode
      - archive → 不写
    """
    name = "memory"

    def process(self, event: dict, importance: dict, appraisal: dict, store) -> dict:
        layer = importance.get("target_memory_layer")
        result: dict = {"written_layers": []}

        if layer == "working":
            mid = self._write_working(event, importance, appraisal, store)
            result["working_memory_id"] = mid
            result["written_layers"].append("working_memory")

        elif layer == "episode_candidate":
            mid = self._write_working(event, importance, appraisal, store)
            result["working_memory_id"] = mid
            result["written_layers"].append("working_memory")
            eid = self._write_episode(event, importance, appraisal, store)
            result["episode_id"] = eid
            result["written_layers"].append("episode")

        elif layer == "archive":
            result["written_layers"].append("none")

        return result

    # ---------- helpers ----------
    def _write_working(self, event, importance, appraisal, store) -> str:
        mid = f"wm-{uuid.uuid4()}"
        store.add_working_memory({
            "memory_id": mid,
            "event_id": event["event_id"],
            "content": event.get("normalized_content", event.get("raw_content", "")),
            "normalized_content": event.get("normalized_content", ""),
            "importance_score": importance["importance_score"],
            "appraisal": appraisal["vector"],
            "source": event.get("source", "cli"),
            "actor": event.get("actor", "user"),
            "created_at": event.get("timestamp", _utc_now()),
            "retrieval_weight": 1.0,
        })
        return mid

    def _write_episode(self, event, importance, appraisal, store) -> str:
        eid = f"episode-{uuid.uuid4()}"
        store.add_episode({
            "episode_id": eid,
            "start_time": event.get("timestamp", _utc_now()),
            "end_time": event.get("timestamp", _utc_now()),
            "summary": event.get("normalized_content", "")[:200],
            "event_ids": [event["event_id"]],
            "actors": [event.get("actor", "user")],
            "outcome": None,
            "importance_score": importance["importance_score"],
            "emotional_trace": appraisal["vector"],
            "created_at": _utc_now(),
        })
        return eid
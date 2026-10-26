"""Slow Loop v0 — Episode Consolidation + Semantic Memory 雏形 + Long Reflection。

流程（对应 ChatGPT Phase 4）：
  读取 recent episodes
  → consolidate episodes（规则聚合，无 embedding/LLM）
  → 从 consolidated / 高重要 episode 提炼 semantic memory 候选
  → 生成 long reflection（只写候选，不更新 belief/relationship/self）
  → 输出 trace（含 episode_ids / event_ids / 跳过原因）

Constitution-lite: 一切产物必须引用 source episode / event，可追溯 evidence。
"""
from __future__ import annotations
import json
import uuid
from datetime import datetime, timezone

from soul.agents.base import BaseAgent

# 内容关键词 → tag（粗略聚合用，不 embedding）
KEYWORD_TAGS = {
    "project soul": "project_soul",
    "evidence": "evidence",
    "memory": "memory",
    "reflection": "reflection",
    "phase": "project_soul",
    "架构": "architecture",
    "方案": "design",
    "模型": "design",
    "采购": "purchase",
    "测试": "testing",
    "新概念": "design",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _tags_for(content: str) -> list[str]:
    low = content.lower()
    tags: list[str] = []
    for key, tag in KEYWORD_TAGS.items():
        if key in low:
            if tag not in tags:
                tags.append(tag)
    return tags


def _jloads(v, default):
    if isinstance(v, list):
        return v
    if not v:
        return default
    try:
        return json.loads(v)
    except Exception:
        return default


class ConsolidationAgent(BaseAgent):
    """把多个相关 episode 聚合为 consolidated episode。规则可解释。"""
    name = "consolidation"

    def process(self, episodes: list[dict]) -> dict:
        """输入：episodes（可含 event_ids_json / summary / actors_json / importance_score）
        输出：{consolidated, result_dict|None, skipped_reason|None}
        """
        if not episodes:
            return {"consolidated": False, "skipped_reason": "no episodes"}

        # 1. actor 相同（且非空）聚合
        actors_set: dict[str, list[dict]] = {}
        for ep in episodes:
            acts = _jloads(ep.get("actors_json"), []) or ["user"]
            key = ",".join(sorted(acts))
            actors_set.setdefault(key, []).append(ep)

        # 取最多人一组聚合
        group = max(actors_set.values(), key=len)
        if len(group) < 2:
            return {"consolidated": False, "skipped_reason": "insufficient episodes (<2 same actor)"}

        # 2. 汇总字段
        event_ids: list[str] = []
        episode_ids = [ep["episode_id"] for ep in group]
        summaries = []
        importances = []
        for ep in group:
            event_ids.extend(_jloads(ep.get("event_ids_json"), []))
            s = (ep.get("summary") or "").strip()
            if s and s not in summaries:
                summaries.append(s)
            importances.append(ep.get("importance_score", 0.0) or 0.0)

        tags: list[str] = []
        for s in summaries:
            for t in _tags_for(s or ""):
                if t not in tags:
                    tags.append(t)

        ce = {
            "consolidated_episode_id": f"ce-{uuid.uuid4()}",
            "source_episode_ids": episode_ids,
            "source_event_ids": [e for e in event_ids if e],
            "start_time": min(ep.get("created_at", _utc_now()) for ep in group),
            "end_time": max(ep.get("created_at", _utc_now()) for ep in group),
            "summary": "；".join(s for s in summaries if s)[:500] or "consolidated episode",
            "actors": list({a for ep in group for a in (_jloads(ep.get("actors_json"), []) or ["user"])}),
            "importance_score": max(importances) if importances else 0.0,
            "emotional_trace": {},
            "tags": tags,
            "consolidation_reason": f"aggregated {len(group)} episodes sharing actor(s), tags={tags}",
            "created_at": _utc_now(),
        }
        return {"consolidated": True, "result": ce, "skipped_reason": None}


class SemanticMemoryAgent(BaseAgent):
    """从 consolidated episode / 高重要 episode 提炼稳定知识。非 belief、非主观。"""
    name = "semantic_memory"

    def process(self, sources: list[dict], source_kind: str = "episode") -> list[dict]:
        """sources: episode 或 consolidated_episode dict 列表。
        产出：semantic memory 候选列表（每条含 content + source_episode_ids + source_event_ids）。
        """
        memories: list[dict] = []
        for src in sources:
            importance = src.get("importance_score", 0.0) or 0.0
            if importance < 0.6:
                continue  # 证据/重要性不足，跳过
            summary = (src.get("summary") or "").strip()
            if not summary:
                continue
            content = _to_knowledge(summary)
            if not content:
                continue
            memories.append({
                "memory_id": f"sem-{uuid.uuid4()}",
                "memory_type": "semantic",
                "content": content,
                "source_episode_ids": (
                    _jloads(src.get("source_episode_ids_json"), [])
                    if "source_episode_ids_json" in src
                    else ([src["episode_id"]] if src.get("episode_id") else [])
                ),
                "source_event_ids": (
                    _jloads(src.get("source_event_ids_json"), src.get("event_ids_json"))
                    if "source_event_ids_json" in src
                    else _jloads(src.get("event_ids_json"), [])
                ),
                "confidence": min(0.9, 0.5 + importance * 0.4),
                "importance": importance,
                "created_at": _utc_now(),
                "updated_at": _utc_now(),
            })
        return memories


def _to_knowledge(summary: str) -> str | None:
    """把 summary 转成稳定的陈述式知识，去除主观判断。规则式。"""
    if not summary:
        return None
    # 去除"反思""尝试""可能"等主观词
    clean = summary
    for w in ("反思", "可能", "似乎", "我觉得", "一定"):
        clean = clean.replace(w, "")
    clean = clean.replace("；", "；").strip()
    if len(clean) < 4:
        return None
    return f"记录：{clean[:180]}"


class SlowLoop:
    """Phase 4 慢速回路：consolidate → semantic memory → long reflection。"""

    def __init__(self, store) -> None:
        self.store = store

    def run(self) -> dict:
        episodes = self.store.list_episodes()
        trace: dict = {
            "episode_ids": [ep["episode_id"] for ep in episodes],
            "event_ids": [],
            "consolidated": False,
        }
        for ep in episodes:
            trace["event_ids"].extend(_jloads(ep.get("event_ids_json"), []))

        # --- Step 1: Consolidation ---
        consol = ConsolidationAgent()
        c_result = consol.process(episodes)
        consolidated = None
        if c_result["consolidated"] and c_result["result"]:
            ce = c_result["result"]
            self.store.add_consolidated_episode(ce)
            consolidated = ce
            trace["consolidated"] = True
            trace["consolidated_episode_id"] = ce["consolidated_episode_id"]
            trace["source_episode_ids"] = list(dict.fromkeys(ce["source_episode_ids"]))
            trace["source_event_ids"] = list(dict.fromkeys(ce["source_event_ids"]))
        else:
            trace["consolidation_skipped"] = c_result["skipped_reason"]

        # --- Step 2: Semantic Memory ---
        sem_agent = SemanticMemoryAgent()
        sem_sources = []
        if consolidated:
            sem_sources.append(consolidated)
        # 高重要单 episode 也可作来源
        for ep in episodes:
            if (ep.get("importance_score", 0.0) or 0.0) >= 0.6:
                sem_sources.append(ep)
        sem_mems = sem_agent.process([s for s in sem_sources if s.get("source_episode_ids_json") is not None or s.get("episode_id")])
        sem_ids = []
        for m in sem_mems:
            self.store.add_semantic_memory(m)
            sem_ids.append(m["memory_id"])
        trace["semantic_memory_ids"] = sem_ids

        # --- Step 3: Long Reflection ---
        long_ref = self._generate_long_reflection(episodes, consolidated, sem_mems)
        if long_ref:
            self.store.add_long_reflection(long_ref)
            trace["long_reflection_id"] = long_ref["reflection_id"]
        else:
            trace["long_reflection_skipped"] = "no episodes"

        trace["used_episode_ids"] = list(dict.fromkeys(trace["episode_ids"]))
        trace["used_event_ids"] = list(dict.fromkeys(trace["event_ids"]))
        return trace

    def _generate_long_reflection(self, episodes, consolidated, sem_mems) -> dict | None:
        if not episodes:
            return None
        event_ids = [e for ep in episodes for e in _jloads(ep.get("event_ids_json"), [])]
        ep_ids = [ep["episode_id"] for ep in episodes]
        ce_id = consolidated["consolidated_episode_id"] if consolidated else None

        observations: list[str] = []
        if consolidated:
            observations.append(
                f"{len(consolidated['source_episode_ids'])} 个 episode 被聚合为一段经历，"
                f"tags={consolidated['tags']}"
            )
        candidates: list[str] = [
            "后续可考虑将该阶段作为 Project Soul 早期构建阶段的 narrative 输入。",
            "后续 Belief Agent 可评估 evidence immutability 是否已成为稳定系统原则。",
        ]
        return {
            "reflection_id": f"ref-long-{uuid.uuid4()}",
            "episode_id": ep_ids[0] if ep_ids else None,
            "consolidated_episode_id": ce_id,
            "event_ids": event_ids,
            "content": "Long reflection: 阶段经历已聚合，产出候选观察。",
            "summary": "阶段经历聚合与候选观察",
            "observations": observations,
            "candidate_updates": candidates,
            "created_at": _utc_now(),
        }
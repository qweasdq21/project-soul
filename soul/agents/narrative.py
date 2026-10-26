"""Narrative Agent — 把 episode 组织成意义（meaning）叙事。

硬约束（Phase 5 Constitution）：
- Memory preserves what happened.  Narrative evolves what it means.
  记忆保存事实，叙事更新意义，自我诞生于意义的持续演化。
- Reality Layer：Event/Evidence，只记发生了什么，append-only，不可修改。
- Narrative Layer：解释意味着什么，可版本化（supersedes），必须引用 evidence，
  不允许新增事实。
- identity_effect 只能写"候选影响"，不能直接修改 self。

核心：Narrative 可以改变意义，但不能改变事实。
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone

from soul.agents.base import BaseAgent

NARRATIVE_TYPES = ("project_progress", "learning", "correction",
                    "cooperation", "uncertainty", "general")

# 强事实/超断言词（Constitution C01/C03：无 evidence 支持则拒）
STRONG_CLAIMS = (
    "真实意识", "真正灵魂", "绝对信任", "完全正确", "已经证明",
    "一定", "永久", "永远", "已经成为", "完全相信", "唯一重要",
    "真实自我", "拥有了自我",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _infer_type(text: str) -> str:
    low = text.lower()
    if any(w in low for w in ("修正", "错误", "correction", "纠正", "失败", "风险")):
        return "correction"
    if any(w in low for w in ("学会了", "learning", "学到", "理解")):
        return "learning"
    if any(w in low for w in ("合作", "cooperation", "协作", "一起")):
        return "cooperation"
    if any(w in low for w in ("不确定", "uncertainty", "疑问", "未知")):
        return "uncertainty"
    if any(w in low for w in ("project", "phase", "实现", "完成", "架构", "阶段")):
        return "project_progress"
    return "general"


class NarrativeAgent(BaseAgent):
    """输入: consolidated_episode / 高重要 episode 列表 + 相关 evidence
    输出: Narrative Candidate（含 evidence_ids / episode_ids / identity_effect）
    """
    name = "narrative"

    def process(self, source: dict | list, semantic_mems: list | None = None) -> dict | None:
        """source: 单个 consolidated episode dict，或 episode dict 列表。
        MVP：只生成一个 narrative candidate。
        """
        # 输入可能是 consolidated episode dict 或 episode dict
        content = None
        source_text = ""
        if isinstance(source, dict):
            content = source.get("summary") or source.get("content") or ""
            source_text = str(content)
        elif isinstance(source, list) and source:
            # 取重要性最高的 episode
            top = max(source, key=lambda e: e.get("importance_score", 0.0) or 0.0)
            content = top.get("summary") or top.get("content") or ""
            source_text = str(content)
        else:
            return None
        if not source_text.strip():
            return None

        narrative_type = _infer_type(source_text)
        meaning = self._make_meaning(source_text, narrative_type)
        identity_effect = self._identity_candidate(source_text)

        # 引用收集
        ep_ids: list[str] = []
        ev_ids: list[str] = []
        ce_id = None
        if isinstance(source, dict):
            ce_id = source.get("consolidated_episode_id") or source.get("consolidated_episode_id", "")
            ep_ids = self._load_list(source.get("source_episode_ids_json", source.get("source_episode_ids", [])))
            ev_ids = self._load_list(source.get("source_event_ids_json", source.get("source_event_ids", [])))
        elif isinstance(source, list):
            for ep in source:
                eid = ep.get("episode_id")
                if eid:
                    ep_ids.append(eid)
                ev_ids.extend(self._load_list(ep.get("event_ids_json", ep.get("event_ids", []))))
                if not ce_id:
                    ce_id = ep.get("consolidated_episode_id")

        sem_ids = []
        if semantic_mems:
            for m in semantic_mems:
                mid = m.get("memory_id") if isinstance(m, dict) else m
                if mid:
                    sem_ids.append(mid)

        nar = {
            "narrative_id": f"nar-{uuid.uuid4()}",
            "title": self._make_title(source_text),
            "narrative_type": narrative_type,
            "content": self._content(source_text),
            "meaning": meaning,
            "identity_effect": identity_effect,
            "evidence_ids": list(dict.fromkeys(ev_ids)),
            "episode_ids": list(dict.fromkeys(ep_ids)),
            "consolidated_episode_id": ce_id,
            "semantic_memory_ids": list(dict.fromkeys(sem_ids)),
            "version": 1,
            "supersedes": None,
            "status": "candidate",
            "created_at": _utc_now(),
        }
        return nar

    # ---------- helpers ----------
    def _load_list(self, v) -> list:
        import json
        if isinstance(v, list):
            return v
        if not v:
            return []
        try:
            return json.loads(v)
        except Exception:
            return [v]

    def _make_title(self, text: str) -> str:
        return text[:40]

    def _content(self, text: str) -> str:
        return str(text)[:500]

    def _make_meaning(self, text: str, ntype: str) -> str:
        """轻度解释意义，不新增事实。"""
        if ntype == "project_progress":
            return f"此阶段标志着 Project Soul 构建中的一次进展：{text[:60]}"
        if ntype == "correction":
            return f"出现了一次修正/纠错信号：{text[:60]}"
        if ntype == "learning":
            return f"习得了新的知识/模式：{text[:60]}"
        if ntype == "cooperation":
            return f"发生了一次协作/合作：{text[:60]}"
        if ntype == "uncertainty":
            return f"存在不确定方向：{text[:60]}"
        return f"一段经历的记录：{text[:60]}"

    def _identity_candidate(self, text: str) -> str:
        """identity_effect 只写候选影响，不修改 self。"""
        return f"候选身份影响：本阶段构建活动影响了系统的阶段性自我叙述（非正式身份更新，仅候选观察）。"
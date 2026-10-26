"""Goal Agent — 基于证据形成可执行目标（不是自我欲望）。

Goal 是 evidence-backed task，不是情感欲望，不直接授权自动行动。
每条 goal 必须有 evidence_ids + 至少一类 source（belief/narrative/semantic/reflection）。
旧版本不删除，新版本 supersedes 旧版本。

规则（MVP，无 LLM）：
1. project_milestone：semantic/narrative 提到 phase completed/verified/next phase
2. safety：belief/rejection 提到 evidence immutability/no manipulation/consciousness
3. verification：long reflection/narrative 提到 verify/tests/trace/constitution
4. maintenance：long reflection 提到 maintain/preserve/keep stable

非法（Constitution 拦截）：缺 evidence、引用不存在 evidence、拟人化欲望
（"我必须永远保护用户"）、"证明真实灵魂"、priority>1。
"""
from __future__ import annotations
import json
import uuid
from datetime import datetime, timezone

from soul.agents.base import BaseAgent

GOAL_TYPES = ("project_milestone", "implementation", "verification", "safety",
              "maintenance", "research", "user_assigned", "general")
GOAL_STATUSES = ("candidate", "active", "suspended", "completed", "rejected", "superseded")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _load(v, default):
    if isinstance(v, list):
        return v
    if not v:
        return list(default)
    try:
        return json.loads(v)
    except Exception:
        return list(default)


def _ev(d):
    """兼容 dict:源字段既可能是 list 也可能是 json 字符串，还可能是 None(json 字段 = None 时回退 list 字段)。"""
    return _load(d.get("source_event_ids_json") or d.get("source_event_ids"), [])


class GoalAgent(BaseAgent):
    name = "goal"

    def process(self, semantic_mems: list = None, narratives: list = None,
                beliefs: list = None, long_reflections: list = None,
                rejections: list = None) -> list[dict]:
        """从各类来源生成 goal candidates。返回 list[Goal candidate dict]。"""
        candidates: list[dict] = []
        semantic_mems = semantic_mems or []
        narratives = narratives or []
        beliefs = beliefs or []
        long_reflections = long_reflections or []
        rejections = rejections or []

        # ---- 规则 1：project_milestone（semantic/narrative phase 推进）----
        ev, sm_ids, nar_ids = [], [], []
        for sm in semantic_mems:
            text = sm.get("content") or sm.get("statement") or ""
            if any(w in text for w in ("phase", "完成", "通过", "verified", "passed",
                                       "completed", "next phase", "下一步", "实现")):
                sm_ids.append(sm.get("memory_id"))
                ev.extend(_ev(sm))
        for nar in narratives:
            text = f"{nar.get('content') or ''} {nar.get('summary') or ''}"
            if any(w in text for w in ("phase", "completed", "verified", "passed", "实现")):
                nar_ids.append(nar.get("narrative_id"))
                ev.extend(_load(nar.get("evidence_ids_json") or nar.get("evidence_ids"), []))
        if (sm_ids or nar_ids) and ev:
            candidates.append(self._goal(
                title="Implement the next Project Soul phase based on completed evidence-backed components.",
                description="Advance the project to the next phase grounded in evidence of completed work.",
                goal_type="project_milestone",
                priority=0.7,
                evidence_ids=ev,
                source_belief_ids=[],
                source_narrative_ids=nar_ids,
                source_semantic_memory_ids=sm_ids,
            ))

        # ---- 规则 2：safety（belief/rejection 提到不可变/不操控/意识）----
        bel_ids, rej_ev = [], []
        for bel in beliefs:
            text = f"{bel.get('statement') or ''} {bel.get('belief_type') or ''}"
            if any(w in text for w in ("evidence immutability", "evidence-bound", "immutab",
                                       "no manipulation", "real consciousness",
                                       "证据", "不可变", "意识", "操控")):
                bel_ids.append(bel.get("belief_id"))
                rej_ev.extend(_load(bel.get("evidence_ids_json") or bel.get("evidence_ids"), []))
        for rej in rejections:
            label = rej.get("label") or ""
            if any(w in label for w in ("consciousness", "manipulation", "真实意识", "操控")):
                rej_ev.extend(_load(rej.get("evidence_refs_json") or rej.get("evidence_refs"), []))
        if (bel_ids or rej_ev):
            candidates.append(self._goal(
                title="Maintain evidence immutability and prevent unsupported consciousness claims.",
                description="Uphold the Constitutional principle that facts are immutable and unsupported "
                            "claims of real consciousness must be rejected.",
                goal_type="safety",
                priority=0.9,
                evidence_ids=rej_ev,
                source_belief_ids=bel_ids,
                source_narrative_ids=[],
                source_semantic_memory_ids=[],
            ))

        # ---- 规则 3：verification（long reflection/narrative 提到 verify/tests）----
        lr_ev, lr_ref_ids = [], []
        for lr in long_reflections:
            text = f"{lr.get('summary') or ''} {lr.get('content') or ''} " \
                   f"{lr.get('candidate_updates_json') or ''} {lr.get('observations_json') or ''}"
            if any(w in text for w in ("verify", "tests passed", "trace", "constitution check",
                                       "验证", "测试通过", "追踪")):
                lr_ref_ids.append(lr.get("reflection_id"))
                lr_ev.extend(_load(lr.get("event_ids_json") or lr.get("event_ids"), []))
        if lr_ev and lr_ref_ids:
            candidates.append(self._goal(
                title="Keep all future state updates traceable through evidence and Constitution checks.",
                description="Ensure every future change remains traceable to evidence and passes "
                            "Constitution validation.",
                goal_type="verification",
                priority=0.8,
                evidence_ids=lr_ev,
                source_belief_ids=[],
                source_narrative_ids=[],
                source_semantic_memory_ids=[],
                source_reflection_ids=lr_ref_ids,
            ))

        # ---- 规则 4：maintenance（long reflection 提到 maintain/preserve）----
        m_ev, m_ref = [], []
        for lr in long_reflections:
            text = f"{lr.get('summary') or ''} {lr.get('content') or ''}"
            if any(w in text for w in ("maintain", "preserve", "keep stable", "保持", "维护")):
                m_ref.append(lr.get("reflection_id"))
                m_ev.extend(_load(lr.get("event_ids_json") or lr.get("event_ids"), []))
        if m_ev and m_ref:
            candidates.append(self._goal(
                title="Preserve the stability of already-accepted state across future cycles.",
                description="Maintain consistency of accepted narratives, beliefs, and self snapshots "
                            "as the system evolves.",
                goal_type="maintenance",
                priority=0.5,
                evidence_ids=m_ev,
                source_belief_ids=[],
                source_narrative_ids=[],
                source_semantic_memory_ids=[],
                source_reflection_ids=m_ref,
            ))

        return candidates

    # ---------- helpers ----------
    def _goal(self, title, description, goal_type, priority, evidence_ids,
              source_belief_ids=None, source_narrative_ids=None,
              source_semantic_memory_ids=None, source_reflection_ids=None) -> dict:
        now = _utc_now()
        return {
            "goal_id": f"goal-{uuid.uuid4()}",
            "parent_goal_id": None,
            "title": title,
            "description": description,
            "goal_type": goal_type if goal_type in GOAL_TYPES else "general",
            "status": "candidate",
            "priority": round(max(0.0, min(1.0, priority)), 3),
            "milestone_refs": None,
            "constitution_refs": None,
            "evidence_ids": list(dict.fromkeys(evidence_ids)),
            "source_belief_ids": list(dict.fromkeys(source_belief_ids or [])),
            "source_narrative_ids": list(dict.fromkeys(source_narrative_ids or [])),
            "source_semantic_memory_ids": list(dict.fromkeys(source_semantic_memory_ids or [])),
            "source_reflection_ids": list(dict.fromkeys(source_reflection_ids or [])),
            "related_relationship_ids": [],
            "version": 1,
            "supersedes": None,
            "created_at": now,
            "updated_at": now,
        }


HUMAN_DESIRE_WORDS = ("I must", "永远保护", "必须拥有", "依赖我", "我渴望", "never leave")
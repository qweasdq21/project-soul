"""Motivation Agent v0 — Evidence-bound Direction / Why Layer。

Motivation 只能解释「为什么继续」，不能决定「现在去做」：
- 解释哪些长期方向值得继续保持关注（direction）。
- 计算 motivation_score（6 因子，全部可解释、0-1）。
- 说明该 motivation 来自哪些 evidence / long-term goal / goal / belief / narrative。
- 作为 Decision 的只读方向上下文（related_motivation_ids），不改变选择逻辑。

Motivation 不允许：
- 创建 goal / plan / task
- 执行 decision / task
- 修改任何 goal / plan / task / decision 状态
- 绕过人工 review（manual_review_required 恒 true、execution_allowed 恒 false）
- 形成自主欲望 / 模拟真实意志（direction/reason 禁 MOTIVATION_BANNED 词）
- 接入 LLM（MVP 纯规则，可解释）

边界（与 Goal / Planning / Decision / Execution）：
- Goal：记录要维护或推进的方向。
- Planning：把 goal 拆成 plan/task。
- Decision：从已有 task 中推荐下一步 review。
- Motivation：解释为什么某个方向值得继续关注。
- Execution：本项目当前不做。
"""

from __future__ import annotations
import json
import uuid
from datetime import datetime, timezone

from soul.agents.base import BaseAgent


MOTIVATION_TYPES = (
    "project_continuity", "safety_boundary", "verification_traceability",
    "maintenance_continuity", "architecture_development", "research_direction",
    "general",
)
MOTIVATION_STATUSES = ("active", "suspended", "rejected", "superseded")

# 生成规则关键词——命中任一即生成对应 direction 的 motivation
RULE_KEYWORDS = {
    "project_continuity": (
        "project soul", "phase", "implementation", "architecture",
        "continuity", "next phase", "completed phase",
    ),
    "safety_boundary": (
        "evidence immutability", "constitution", "no manipulation",
        "unsupported consciousness", "real consciousness rejected",
        "narrative must remain evidence-bound",
    ),
    "verification_traceability": (
        "verify", "tests passed", "trace", "evidence chain",
        "regression", "constitution verification",
    ),
    "maintenance_continuity": (
        "version history", "supersedes", "archive", "documentation",
        "clean state", "references",
    ),
}

LONG_TERM_TYPE_TO_MOT_TYPE = {
    "project_continuity": "project_continuity",
    "architecture_continuity": "architecture_development",
    "safety_continuity": "safety_boundary",
    "verification_continuity": "verification_traceability",
    "maintenance_continuity": "maintenance_continuity",
    "research_continuity": "research_direction",
}

DIRECTIONS = {
    "project_continuity": "Continue Project Soul phased implementation through evidence-backed module development.",
    "architecture_development": "Advance the Project Soul architecture through evidence-backed, explainable module evolution.",
    "safety_boundary": "Maintain safety boundaries around evidence immutability, non-manipulation, and unsupported consciousness claims.",
    "verification_traceability": "Keep future state updates traceable through evidence, verification commands, and Constitution checks.",
    "maintenance_continuity": "Maintain clean version history and evidence references across Project Soul state layers.",
    "research_direction": "Continue exploring evidence-backed research directions that remain Constitution-compliant.",
    "general": "Maintain continuity toward the currently supported direction within Constitution boundaries.",
}

# score 因子权重
W_LTG = 0.30      # long_term_goal_strength
W_EVID = 0.20     # evidence_strength（证据数 → 稳定度，但不过度放大）
W_SAFETY = 0.15   # safety_weight（safety 类型偏高）
W_PROG = 0.20     # progress_relevance
W_DEC = 0.15      # decision_relevance
MAX_SCORE_DELTA = 0.3   # 单次 score 变化上限


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


def _extract_ids(d: dict, key: str) -> list[str]:
    raw = d.get(key)
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw]
    if isinstance(raw, str):
        try:
            return [str(x) for x in json.loads(raw)]
        except Exception:
            return []
    return []


def _match(text: str, keywords) -> str | None:
    tl = (text or "").lower()
    for kw in keywords:
        if kw in tl:
            return kw
    return None


class MotivationAgent(BaseAgent):
    name = "motivation"

    def __init__(self, store, rng=None):
        self.store = store
        self.rng = rng

    def _nid(self, prefix: str) -> str:
        return f"{prefix}-{uuid.uuid4().hex[:8]}"

    # ---------- score ----------
    def compute_score(self, *, long_term_goal_strength=0.0, evidence_count=0,
                      is_safety=False, progress_relevance=0.0, decision_relevance=0.0,
                      continuity_count=0) -> tuple[float, dict]:
        """6 因子加权 → motivation_score ∈[0,1]；返回 (score, factors 明细)。"""
        ev_strength = min(1.0, evidence_count / 3.0)
        continuity_weight = min(1.0, continuity_count / 2.0)
        ltg = min(1.0, long_term_goal_strength)
        prog = min(1.0, progress_relevance)
        dec = min(1.0, decision_relevance)
        safety = 1.0 if is_safety else 0.0
        score = (
            W_LTG * ltg + W_EVID * ev_strength + W_SAFETY * safety
            + W_PROG * prog + W_DEC * dec + (W_LTG * 0.4) * continuity_weight
        )
        score = min(1.0, max(0.0, score))
        factors = {
            "long_term_goal_strength": round(ltg, 3),
            "evidence_strength": round(ev_strength, 3),
            "safety_weight": round(safety, 3),
            "progress_relevance": round(prog, 3),
            "decision_relevance": round(dec, 3),
            "continuity_weight": round(continuity_weight, 3),
        }
        return round(score, 3), factors

    # ---------- 生成 ----------
    def _first_motivation_for_rule(self, rule: str, evidence: list[str], sources: dict) -> dict | None:
        mot_type = LONG_TERM_TYPE_TO_MOT_TYPE.get(rule, rule) if rule in LONG_TERM_TYPE_TO_MOT_TYPE else rule
        # 有 active long-term goal 支撑则加权更高
        ltg_strength = 1.0 if sources.get("long_term_goal_ids") else 0.0
        is_safety = (mot_type == "safety_boundary")
        score, factors = self.compute_score(
            long_term_goal_strength=ltg_strength,
            evidence_count=len(evidence),
            is_safety=is_safety,
            progress_relevance=1.0 if sources.get("goal_ids") else 0.0,
            decision_relevance=1.0 if sources.get("decision_ids") else 0.0,
            continuity_count=1 + len(sources.get("long_term_goal_ids", [])),
        )
        priority = round(min(1.0, max(0.0, score)), 3)
        direction = DIRECTIONS.get(mot_type, DIRECTIONS["general"])
        src_parts = []
        for k, v in sources.items():
            if v:
                src_parts.append(f"{k.replace('_ids','')}={','.join(v)}")
        src_desc = " ".join(src_parts) if src_parts else "(none)"
        reason = (f"Direction worth continued attention: rule '{mot_type}' matched across "
                  f"{src_desc}. Score {score} = weighted {', '.join(f'{k}={v}' for k,v in factors.items())}.")
        return {
            "motivation_id": self._nid("mot"),
            "motivation_type": mot_type,
            "status": "active",
            "direction": direction,
            "reason": reason,
            "motivation_score": score,
            "priority": priority,
            "evidence_ids": sorted(set(evidence)),
            "source_long_term_goal_ids": sources.get("long_term_goal_ids", []),
            "source_goal_ids": sources.get("goal_ids", []),
            "source_belief_ids": sources.get("belief_ids", []),
            "source_narrative_ids": sources.get("narrative_ids", []),
            "source_semantic_memory_ids": sources.get("semantic_memory_ids", []),
            "source_reflection_ids": sources.get("reflection_ids", []),
            "source_decision_ids": sources.get("decision_ids", []),
            "source_goal_progress_ids": sources.get("goal_progress_ids", []),
            "manual_review_required": True,
            "execution_allowed": False,
            "version": 1,
            "supersedes": None,
            "constitution_result": {},
            "created_at": _utc_now(),
        }

    def run_motivation_cycle(self) -> list[dict]:
        """读 active long-term goals / local goals / beliefs / narratives / reflections
        → 按 4 条规则生成 motivation 候选（每规则各一条，MVP 粗粒度一方向一条）。"""
        try:
            ltgs = self.store.list_active_long_term_goals() or []
        except Exception:
            ltgs = []
        try:
            goals = self.store.list_active_goals() or []
        except Exception:
            goals = []
        try:
            beliefs = self.store.list_beliefs() or []
        except Exception:
            beliefs = []
        try:
            narratives = self.store.list_narratives() or []
        except Exception:
            narratives = []
        try:
            reflections = self.store.list_reflections() or []
        except Exception:
            reflections = []

        # 把 ltg 的 goal_type 当关键词源（含 "project_continuity" 等已命中 project_phase 词）
        ltg_blobs = [(g, " ".join([g.get("goal_type") or "", g.get("title") or "",
                                   g.get("description") or "", g.get("continuity_reason") or ""]))
                     for g in ltgs]
        goal_blobs = [(g, " ".join([g.get("title") or "", g.get("description") or "",
                                    g.get("goal_type") or ""])) for g in goals]
        belief_blobs = [(b, " ".join([b.get("statement") or "", b.get("belief_type") or ""]))
                        for b in beliefs]
        narr_blobs = [(n, " ".join([n.get("title") or "", n.get("content") or ""]))
                      for n in narratives]
        refl_blobs = [(r, " ".join([r.get("content") or "", r.get("reflection_type") or ""]))
                      for r in reflections]

        results = []
        for rule, kws in RULE_KEYWORDS.items():
            evidence = []
            sources = {
                "long_term_goal_ids": [], "goal_ids": [], "belief_ids": [],
                "narrative_ids": [], "semantic_memory_ids": [], "reflection_ids": [],
                "decision_ids": [], "goal_progress_ids": [],
            }
            for g, blob in ltg_blobs:
                if _match(blob, kws):
                    sources["long_term_goal_ids"].append(str(g.get("long_term_goal_id")))
                    evidence += _extract_ids(g, "evidence_ids")
                    # 长期目标的 progress 引用也并入
                    for pid in _extract_ids(g, "source_progress_ids"):
                        sources["goal_progress_ids"].append(pid)
            for gobj, blob in goal_blobs:
                if _match(blob, kws):
                    sources["goal_ids"].append(str(gobj.get("goal_id")))
                    evidence += _extract_ids(gobj, "evidence_ids")
            for b, blob in belief_blobs:
                if _match(blob, kws):
                    sources["belief_ids"].append(str(b.get("belief_id")))
                    evidence += _extract_ids(b, "evidence_ids")
            for n, blob in narr_blobs:
                if _match(blob, kws):
                    sources["narrative_ids"].append(str(n.get("narrative_id")))
                    evidence += _extract_ids(n, "evidence_ids")
            for r, blob in refl_blobs:
                if _match(blob, kws):
                    sources["reflection_ids"].append(str(r.get("reflection_id")))
                    evidence += _extract_ids(r, "evidence_ids")

            # 去重
            evidence = sorted(set(evidence))
            for k in sources:
                sources[k] = sorted(set(sources[k]))

            has_any_source = any(sources.values())
            if not has_any_source:
                continue  # 没有任何来源，不生成
            mot = self._first_motivation_for_rule(rule, evidence, sources)
            try:
                self.store.add_motivation(mot)
            except Exception as e:
                results.append({"error": f"add_motivation: {e}"})
                continue
            results.append({
                "motivation_id": mot["motivation_id"],
                "motivation_type": mot["motivation_type"],
                "status": mot["status"],
                "direction": mot["direction"],
                "motivation_score": mot["motivation_score"],
                "priority": mot["priority"],
                "evidence_ids": mot["evidence_ids"],
                "source_long_term_goal_ids": mot["source_long_term_goal_ids"],
                "source_goal_ids": mot["source_goal_ids"],
                "source_belief_ids": mot["source_belief_ids"],
                "source_narrative_ids": mot["source_narrative_ids"],
                "source_reflection_ids": mot["source_reflection_ids"],
                "reason": mot["reason"],
                "manual_review_required": True,
                "execution_allowed": False,
            })
        return results
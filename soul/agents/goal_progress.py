"""Goal Priority + Goal Progress Agent — Phase 9。

Goal Priority（computed_priority）：
可解释优先级，6 因子加权，跳变 ≤ 0.3，变化记录 reason + evidence。

Goal Progress（goal_progress）：
MVP 规则生成 progress（0-1），completed_candidate ≠ completed。
每条必须引 evidence；单次 delta ≤ 0.35；不得自动改 goal status 为 completed。
"""
from __future__ import annotations
import json
import uuid
from datetime import datetime, timezone

from soul.agents.base import BaseAgent

PROGRESS_STATUSES = (
    "not_started", "in_progress", "blocked", "waiting_for_evidence",
    "ready_for_review", "completed_candidate",
)

# computed_priority 6 因子权重（可解释）
PRIO_W = {
    "base": 0.20,         # 1. base_priority：基础优先级，goal_type 决定
    "safety": 0.20,       # 2. safety_weight：safety/verification 较高
    "stage": 0.15,        # 3. project_stage_relevance：与当前阶段相关
    "unfinished": 0.15,   # 4. unfinished_weight：active 且未完成更高
    "recent": 0.15,       # 5. recent_activity：最近有 evidence 更高
    "dependency": 0.15,   # 6. dependency_weight：被未来依赖更高
}

GOAL_TYPE_BASE = {
    "safety": 0.9, "verification": 0.8, "project_milestone": 0.7,
    "implementation": 0.6, "maintenance": 0.5, "research": 0.4,
    "user_assigned": 0.8, "general": 0.5,
}


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


class PriorityAgent:
    """计算 goal 的 computed_priority（6 因子，可解释）。"""

    name = "goal_priority"

    def compute(self, goal: dict, previous_priority: float | None = None) -> dict:
        gtype = goal.get("goal_type", "general")
        base = GOAL_TYPE_BASE.get(gtype, 0.5)
        # 2. safety_weight：safety/verification 更高
        safety = 0.0
        if gtype in ("safety", "verification"):
            safety = 0.2
        # 3. project_stage_relevance：标题含 phase 相关词
        stage = 0.0
        text = (goal.get("title") or "") + " " + (goal.get("description") or "")
        if any(w in text for w in ("phase", "Project Soul", "next phase")):
            stage = 0.15
        # 4. unfinished_weight：active 且未完成更高
        unfinished = 0.15 if goal.get("status") == "active" else 0.0
        # 5. recent_activity：最近有 evidence（updated_at 非空且非初始）
        recent = 0.05 if goal.get("updated_at") else 0.0
        # 6. dependency_weight：本 MVP safety/verification 视为被依赖
        dependency = 0.1 if gtype in ("safety", "verification") else 0.05

        raw = (PRIO_W["base"] * base + PRIO_W["safety"] * safety
               + PRIO_W["stage"] * stage + PRIO_W["unfinished"] * unfinished
               + PRIO_W["recent"] * recent + PRIO_W["dependency"] * dependency)
        computed = round(max(0.0, min(1.0, raw)), 3)

        # 跳变 ≤ 0.3
        reason_parts = [f"base(type={gtype})={base}",
                        f"safety_weight={safety:.2f}",
                        f"stage_relevance={stage:.2f}",
                        f"unfinished={unfinished:.2f}",
                        f"recent={recent:.2f}",
                        f"dependency={dependency:.2f}"]
        if previous_priority is not None:
            delta = computed - previous_priority
            if abs(delta) > 0.3:
                computed = round(previous_priority + (0.3 if delta > 0 else -0.3), 3)
                reason_parts.append(f"clamped delta≤0.3 (was {delta:+.2f})")
        reason = "computed_priority = " + " + ".join(reason_parts)
        return {
            "computed_priority": computed,
            "priority_reason": reason,
            "factors": {k: round(v, 3) for k, v in {
                "base": base, "safety": safety, "stage": stage,
                "unfinished": unfinished, "recent": recent, "dependency": dependency,
            }.items()},
        }


class ProgressAgent(BaseAgent):
    """基于规则从各类来源为准 goal 生成 progress 记录。"""

    name = "goal_progress"

    def process(self, goals: list = None, semantic_mems: list = None,
                narratives: list = None, reflections: list = None,
                rejections: list = None,
                latest_progress: dict | None = None) -> list[dict]:
        """为 goals 生成 progress candidates。每 goal 最多产生一条本轮 progress。
        latest_progress: {goal_id: latest_progress_record}，用于累计 progress_value。"""
        candidates: list[dict] = []
        goals = goals or []
        semantic_mems = semantic_mems or []
        narratives = narratives or []
        reflections = reflections or []
        rejections = rejections or []
        latest_progress = latest_progress or {}

        for goal in goals:
            if goal.get("status") != "active":
                continue
            goal_id = goal.get("goal_id")
            gtype = goal.get("goal_type")
            latest = latest_progress.get(goal_id)

            # 收集与 goal 相关的 evidence（来源里含 goal 关键词）
            related = self._find_related(goal, semantic_mems, narratives, reflections)
            if not related:
                # 规则 4：缺乏新 evidence
                if not (semantic_mems or narratives or reflections):
                    candidates.append(self._progress(
                        goal, 0.0, "waiting_for_evidence", [],
                        "No new related evidence yet.", latest=latest,
                    ))
                else:
                    candidates.append(self._progress(
                        goal, 0.0, "waiting_for_evidence", [],
                        "No new evidence matched this goal this cycle.", latest=latest,
                    ))
                continue

            # 规则 5：阻塞
            blocked = any(w in (r.get("content") or "") + " " + (r.get("summary") or "")
                          for r in rejections for w in ("blocked", "failed", "reject",
                                                        "invalid", "错误", "失败", "拒绝"))
            if blocked:
                candidates.append(self._progress(
                    goal, -0.05, "blocked", related["ev"],
                    "Recent evidence indicates the goal is blocked or rejected.", latest=latest,
                ))
                continue

            # 规则 1：phase 完成证据 → +0.2 ~ +0.35
            text = related["text"]
            if any(w in text for w in ("completed", "passed", "verified", "完成", "通过", "验证通过")):
                cand = self._progress(
                    goal, 0.25, "in_progress", related["ev"],
                    "Related verification evidence indicates traceability checks passed.",
                    latest=latest,
                )
                if gtype == "safety":
                    cand["progress_delta"] = min(0.15, cand["progress_delta"])
                    cand["progress_value"] = round(
                        max(0.0, min(1.0, (float(latest["progress_value"]) if latest else 0.0)
                                     + cand["progress_delta"])), 3)
                    cand["reason"] = "Safety goal: a single pass only small increment."
                elif float(cand["progress_value"]) >= 1.0:
                    cand["progress_status"] = "completed_candidate"
                    cand["reason"] += " Suggest completed_candidate for review."
                candidates.append(cand)
                continue

            # 规则 2：实现中证据 → +0.1 ~ +0.2
            if any(w in text for w in ("started", "implementing", "cycle", "实现", "开始", "进入")):
                candidates.append(self._progress(
                    goal, 0.15, "in_progress", related["ev"],
                    "Implementation evidence indicates the goal is in progress.", latest=latest,
                ))
                continue

            # 未匹配具体规则但相关 → 小幅
            candidates.append(self._progress(
                goal, 0.05, "in_progress", related["ev"],
                "Related evidence present but no phase/implementation signal detected.",
                latest=latest,
            ))

        return candidates

    # ---------- helpers ----------
    def _find_related(self, goal, semantic_mems, narratives, reflections) -> dict | None:
        """找与 goal 相关的来源文本 + evidence。按 goal_type 关键词匹配。"""
        gtype = goal.get("goal_type")
        goal_words = {
            "safety": ("immutab", "consciousness", "manipulation", "证据", "意识", "操控"),
            "verification": ("trace", "constitution check", "verify", "验证", "追踪"),
            "project_milestone": ("phase", "completed", "实现", "implement", "阶段"),
            "maintenance": ("maintain", "preserve", "stability", "保持"),
        }.get(gtype, (goal.get("title") or "")[:8])
        ev, parts = [], []
        for sm in semantic_mems:
            c = sm.get("content") or ""
            if any(w in c.lower() for w in goal_words):
                parts.append(c)
                ev.extend(_load(sm.get("source_event_ids_json") or sm.get("source_event_ids"), []))
        for n in narratives:
            c = (n.get("summary") or "") + " " + (n.get("content") or "")
            if any(w in c.lower() for w in goal_words):
                parts.append(c)
                ev.extend(_load(n.get("evidence_ids_json") or n.get("evidence_ids"), []))
        for lr in reflections:
            c = lr.get("summary") or lr.get("content") or ""
            if any(w in c.lower() for w in goal_words):
                parts.append(c)
                ev.extend(_load(lr.get("event_ids_json") or lr.get("event_ids"), []))
        if not parts:
            return None
        return {"text": " ".join(parts), "ev": list(dict.fromkeys(ev))}

    def _progress(self, goal, delta, status, evidence_ids, reason,
                  latest=None) -> dict:
        latest_val = float(latest.get("progress_value", 0.0)) if latest else 0.0
        v = round(max(0.0, min(1.0, latest_val + delta)), 3)
        d = round(max(-1.0, min(0.35, delta)), 3)
        return {
            "progress_id": f"gp-{uuid.uuid4()}",
            "goal_id": goal.get("goal_id"),
            "progress_value": v,
            "progress_delta": d,
            "progress_status": status,
            "evidence_ids": list(dict.fromkeys(evidence_ids)),
            "source_episode_ids": [],
            "source_narrative_ids": [],
            "source_semantic_memory_ids": [],
            "source_reflection_ids": [],
            "source_goal_update_ids": [],
            "reason": reason,
            "created_at": _utc_now(),
        }
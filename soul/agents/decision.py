"""Decision Agent — 从现有 goal/plan/task 里推荐"下一步人工 review"的 task（不是行动）。

Decision 只给 review 建议，不给执行许可：
- 选择现有 goals / plans / tasks 中一个最适合作为"下一步"的 task。
- 说明为什么选它（decision_factors + reason，全部可解释、中性工程描述）。
- manual_review_required=True（必须人工复核）、execution_allowed=False（不授权执行）。
- 不新建 plan / 不新建 goal / 不改变 task/plan/goal status / 不模拟欲望 / 不调用任何工具。

规则（MVP，无 LLM）：
1. 按 computed_priority（无则 base priority）降序选 active goal。
2. 选该 goal 下最新 proposed/active plan（排除 completed/rejected/superseded）。
3. 选 plan 下第一个未被依赖阻塞的 proposed/ready task；有依赖未满足 → review_required。
4. safety/verification goal 在 priority 接近最高时可优先推荐，但不无限压制 implementation。
5. 无可选 task → decision_type = defer / blocked（说明原因）。
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone

from soul.agents.base import BaseAgent

DECISION_TYPES = ("next_task_recommendation", "defer", "review_required", "blocked", "general")
DECISION_STATUSES = ("proposed", "waiting_for_review", "rejected", "superseded")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _load(v, default):
    if isinstance(v, list):
        return v
    if not v:
        return list(default)
    try:
        import json
        return json.loads(v)
    except Exception:
        return list(default)


def _ev(d):
    return _load(d.get("source_event_ids_json") or d.get("source_event_ids"), [])


class DecisionAgent(BaseAgent):
    name = "decision"

    def process(self, goals: list = None, goal_progress: dict = None,
                plans: list = None, tasks: list = None,
                beliefs: list = None, narratives: list = None,
                semantic_mems: list = None,
                long_term_goals: list = None,
                motivations: list = None) -> list[dict]:
        """返回 list[Decision candidate dict]（通常 1 个，也可能 0 个=无 action）。
        long_term_goals: 可选，active long-term goals，用于给 decision 附加长期上下文
        （related_long_term_goal_ids + continuity_context），仅只读，不改变选择逻辑。
        motivations: 可选，active motivations，只读方向上下文（related_motivation_ids）。"""
        goals = goals or []
        goal_progress = goal_progress or {}
        plans = plans or []
        tasks = tasks or []
        beliefs = beliefs or []
        narratives = narratives or []
        semantic_mems = semantic_mems or []
        long_term_goals = long_term_goals or []
        motivations = motivations or []

        # 规则1：按 computed_priority 降序选 active goal
        goal_key = lambda g: float(g.get("computed_priority") or g.get("priority") or 0.0)
        sorted_goals = sorted(goals, key=goal_key, reverse=True)
        if not sorted_goals:
            return [self._decision(None, None, None, "defer",
                                   "No active goal available to recommend a next step.")]

        candidates: list[dict] = []
        for goal in sorted_goals:
            gid = goal.get("goal_id")
            cand = self._try_goal(goal, goals, goal_progress, plans, tasks,
                                  beliefs, narratives, semantic_mems, long_term_goals, motivations)
            if cand:
                candidates.append(cand)
                # 规则4：不要无限压制 implementation —— 只收集 1 个 recommendation
                break
        if not candidates:
            # 规则5：兜底 —— 没有任何可选 task
            top = sorted_goals[0]
            return [self._decision_with_factors(
                selected=None, dtype="blocked",
                reason="No proposed/ready task is currently selectable across active goals.",
            )]
        return candidates

    # ---------- 单个 goal 的选择 ----------
    def _try_goal(self, goal, goals, goal_progress, plans, tasks,
                  beliefs, narratives, semantic_mems, long_term_goals=None, motivations=None) -> dict | None:
        gid = goal.get("goal_id")
        gtype = goal.get("goal_type", "general")
        priority = float(goal.get("computed_priority") or goal.get("priority") or 0.0)
        lp = goal_progress.get(gid) or {}
        # Phase 12：找包含该 goal 的 active long-term goals（只读附加上下文）
        related_ltg, continuity_ctx = [], None
        for ltg in (long_term_goals or []):
            src = _load(ltg.get("source_goal_ids_json") or ltg.get("source_goal_ids"), [])
            if gid in src:
                related_ltg.append(ltg.get("long_term_goal_id"))
                if continuity_ctx is None:
                    continuity_ctx = {
                        "goal_type": ltg.get("goal_type"),
                        "priority": ltg.get("priority"),
                        "progress_value": ltg.get("progress_value"),
                        "status": ltg.get("status"),
                    }
        # Phase 13：找涉及该 goal 的 active motivations（只读方向上下文）
        related_mot_ids = []
        for m in (motivations or []):
            m_src = _load(m.get("source_goal_ids_json") or m.get("source_goal_ids"), [])
            m_ltg = _load(m.get("source_long_term_goal_ids_json") or m.get("source_long_term_goal_ids"), [])
            if gid in m_src or any(lt in related_ltg for lt in m_ltg):
                related_mot_ids.append(m.get("motivation_id"))
        # 规则2：选该 goal 下最新 proposed/active plan
        g_plans = [p for p in plans
                   if p.get("goal_id") == gid and p.get("status") in ("proposed", "active")]
        if not g_plans:
            return self._decision(None, None, None, "defer",
                                  f"Goal {gid} has no active/proposed plan to recommend from. "
                                  "Run planning-cycle first.")
        # 选最新 plan（若多个取最近 created）
        plan = sorted(g_plans, key=lambda p: p.get("created_at") or "", reverse=True)[0]
        pid = plan.get("plan_id")
        plan_evidence = _load(plan.get("evidence_ids_json") or plan.get("evidence_ids"), [])
        # 规则3：选 plan 下第一个未被依赖阻塞的 proposed/ready task
        plan_tasks = [t for t in tasks if t.get("plan_id") == pid]
        plan_tasks.sort(key=lambda t: t.get("order_index") or 0)
        selectable = [t for t in plan_tasks if t.get("status") in ("proposed", "ready")]
        if not selectable:
            return self._decision(gid, pid, None, "defer",
                                  f"Plan {pid} has no proposed/ready task to recommend.")
        task = selectable[0]
        tid = task.get("task_id")
        deps = _load(task.get("depends_on_task_ids_json") or task.get("depends_on_task_ids"), [])
        dep_status = "met"
        for d in deps:
            dep = next((t for t in plan_tasks if t.get("task_id") == d), None)
            if not dep or dep.get("status") not in ("completed", "completed_candidate"):
                dep_status = f"blocked_by_{d}"
                break
        task_evidence = _load(task.get("evidence_ids_json") or task.get("evidence_ids"), [])
        evidence = list(dict.fromkeys(plan_evidence + task_evidence))
        # factors（全部可解释）
        safety_w = 0.3 if gtype == "safety" else 0.0
        verif_w = 0.25 if gtype == "verification" else 0.0
        factors = {
            "goal_priority": round(priority, 3),
            "goal_progress_value": lp.get("progress_value"),
            "goal_progress_status": lp.get("progress_status"),
            "plan_status": plan.get("status"),
            "task_order_index": task.get("order_index"),
            "task_status": task.get("status"),
            "dependency_status": dep_status,
            "safety_weight": safety_w,
            "verification_weight": verif_w,
            "evidence_strength": round(min(1.0, len(evidence) / 3.0), 3),
            "constitution_state": "all_checks_pass" if plan.get("constitution_result") else "unknown",
        }
        reason = (f"Selected task {tid} because it belongs to the highest-priority active goal "
                  f"({gtype}, priority={priority:.2f}), its plan {pid} is {plan.get('status')}, "
                  f"and the task is the first pending task with evidence-backed references "
                  f"({len(evidence)} evidence). Dependency: {dep_status}. "
                  f"Review required; no execution permission.")
        selected = {
            "decision_id": f"decision-{uuid.uuid4()}",
            "decision_type": ("review_required" if dep_status != "met"
                              else "next_task_recommendation"),
            "status": "waiting_for_review",
            "selected_goal_id": gid,
            "selected_plan_id": pid,
            "selected_task_id": tid,
            "selected_task_title": task.get("title", ""),
            "reason": reason,
            "decision_factors": factors,
            "evidence_ids": evidence,
            "source_goal_ids": [gid],
            "source_plan_ids": [pid],
            "source_task_ids": [tid],
            "source_belief_ids": [],
            "source_narrative_ids": [],
            "source_semantic_memory_ids": [],
            "source_goal_progress_ids": [lp.get("progress_id")] if lp.get("progress_id") else [],
            "related_long_term_goal_ids": related_ltg,
            "continuity_context": continuity_ctx,
            "related_motivation_ids": related_mot_ids,
            "manual_review_required": True,
            "execution_allowed": False,
            "constitution_result": {},
            "created_at": _utc_now(),
        }
        return selected

    # ---------- helpers ----------
    def _decision(self, gid, pid, tid, dtype, reason) -> dict:
        return self._decision_with_factors(
            selected={"selected_goal_id": gid, "selected_plan_id": pid, "selected_task_id": tid},
            dtype=dtype, reason=reason,
        )

    def _decision_with_factors(self, selected, dtype, reason) -> dict:
        factors = {
            "goal_priority": None, "goal_progress_value": None,
            "goal_progress_status": None, "plan_status": None,
            "task_order_index": None, "task_status": None, "dependency_status": "n/a",
            "safety_weight": 0.0, "verification_weight": 0.0,
            "evidence_strength": 0.0, "constitution_state": "n/a",
        }
        now = _utc_now()
        dec = {
            "decision_id": f"decision-{uuid.uuid4()}",
            "decision_type": dtype if dtype in DECISION_TYPES else "general",
            "status": "waiting_for_review",
            "selected_goal_id": selected.get("selected_goal_id"),
            "selected_plan_id": selected.get("selected_plan_id"),
            "selected_task_id": selected.get("selected_task_id"),
            "selected_task_title": "",
            "reason": reason,
            "decision_factors": factors,
            "evidence_ids": [],
            "source_goal_ids": selected.get("selected_goal_id") and [selected["selected_goal_id"]] or [],
            "source_plan_ids": selected.get("selected_plan_id") and [selected["selected_plan_id"]] or [],
            "source_task_ids": selected.get("selected_task_id") and [selected["selected_task_id"]] or [],
            "source_belief_ids": [],
            "source_narrative_ids": [],
            "source_semantic_memory_ids": [],
            "source_goal_progress_ids": [],
            "manual_review_required": True,
            "execution_allowed": False,
            "constitution_result": {},
            "created_at": now,
        }
        return dec
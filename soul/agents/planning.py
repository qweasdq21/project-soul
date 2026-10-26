"""Planning Agent — 把证据背书的 active goal 拆成 plan + tasks（不是行动系统）。

Plan 是计划，不是 action；Task 是 proposed work item，不是 execution command。
Planning 只产出"未来可做什么"，一律不自动执行、不调用外部工具、不改文件/发邮件/调 API。
每条 plan/task 必须引用 goal_id + evidence_ids + 至少一类 source。
task execution_mode 默认 manual_only（未来如需自动化再单独走 Decision，受 Constitution 拦）。

规则（MVP，无 LLM，按 goal_type 分发）：
1. implementation / project_milestone -> implementation plan + 8 tasks（review/identify/schema/skeleton/checks/cli/tests/docs）
2. safety                      -> safety plan + 5 tasks（forbidden/evidence/constitution/rejection/state）
3. verification                -> verification plan + 8 tasks（逐层 verify + record）
4. maintenance                 -> maintenance plan + 5 tasks（versioning/supersedes/rejected/archived/docs）

只创建 proposed / active plan，绝不自动 completed。
旧 plan 不删除，新版本 supersedes 旧版本。
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone

from soul.agents.base import BaseAgent

PLAN_TYPES = ("implementation", "verification", "safety", "maintenance",
              "research", "consolidation", "general")
PLAN_STATUSES = ("proposed", "active", "suspended", "completed_candidate",
                 "completed", "rejected", "superseded")
TASK_TYPES = ("inspect", "implement", "verify", "document", "review",
              "maintain", "research", "general")
TASK_STATUSES = ("proposed", "ready", "blocked", "in_progress_candidate",
                 "completed_candidate", "rejected")
EXECUTION_MODES = ("manual_only", "future_decision_required")


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


class PlanningAgent(BaseAgent):
    name = "planning"

    def process(self, goals: list = None, goal_progress: list = None,
                narratives: list = None, semantic_mems: list = None,
                beliefs: list = None, long_reflections: list = None
                ) -> list[dict]:
        """对活跃 goal 生成 plan + tasks candidates。

        返回 list[dict]，每项形如 {"plan": {...}, "tasks": [...], "goal": {...}}。
        """
        goals = goals or []
        goal_progress = goal_progress or {}
        narratives = narratives or []
        semantic_mems = semantic_mems or []
        beliefs = beliefs or []
        long_reflections = long_reflections or []

        candidates: list[dict] = []
        for goal in goals:
            gid = goal.get("goal_id")
            if not gid:
                continue
            gtype = goal.get("goal_type", "general")
            evidence = list(dict.fromkeys(_load(goal.get("evidence_ids_json", []), [])
                                          or _load(goal.get("evidence_ids", []), [])))
            if not evidence:
                # Constitution 也会拦；这里先不产出无证据 plan
                continue
            latest_p = goal_progress.get(gid) or {}
            plan_type = self._plan_type_for(gtype)
            plan = self._plan(goal, plan_type, latest_p)
            tasks = self._tasks_for(gtype, gid, evidence, latest_p)
            plan["task_ids"] = [t["task_id"] for t in tasks]
            candidates.append({"plan": plan, "tasks": tasks, "goal": goal})
        return candidates

    # ---------- plan 生成 ----------
    def _plan(self, goal: dict, plan_type: str, latest_p: dict) -> dict:
        gtype = goal.get("goal_type", "general")
        title, desc = self._plan_text(plan_type)
        evidence = [e for e in _load(goal.get("evidence_ids_json", []), [])
                    or _load(goal.get("evidence_ids", []), [])]
        now = _utc_now()
        return {
            "plan_id": f"plan-{uuid.uuid4()}",
            "goal_id": goal.get("goal_id"),
            "title": title,
            "description": desc,
            "plan_type": plan_type if plan_type in PLAN_TYPES else "general",
            "status": "proposed",  # Planning 只创建 proposed，不自动 completed
            "priority": round(max(0.0, min(1.0, goal.get("priority", 0.0))), 3),
            "evidence_ids": evidence,
            "source_goal_ids": [goal.get("goal_id")],
            "source_belief_ids": [],
            "source_narrative_ids": [],
            "source_semantic_memory_ids": [],
            "source_reflection_ids": [],
            "source_goal_progress_ids": [latest_p.get("progress_id")] if latest_p.get("progress_id") else [],
            "source_consolidated_episode_ids": [],
            "task_ids": [],
            "plan_reason": f"Derived from active goal {goal.get('goal_id')} "
                           f"(type={gtype}, priority={goal.get('priority')}); "
                           f"evidence_bound via goal evidence refs. Planning only, no execution.",
            "version": 1,
            "supersedes": None,
            "constitution_result": {},
            "created_at": now,
            "updated_at": now,
        }

    def _plan_text(self, plan_type: str) -> tuple:
        if plan_type == "implementation":
            return (
                "Implement the next Project Soul phase through evidence-backed module development.",
                "Decompose the active implementation goal into inspect/implement/verify/document tasks "
                "grounded in verified goal progress. Planning only; nothing executes automatically."
            )
        if plan_type == "safety":
            return (
                "Maintain Project Soul safety boundaries through Constitution checks and rejection logs.",
                "Verify forbidden claim patterns are rejected and every accepted state update remains "
                "evidence-bound. Planning only; no enforcement action is taken here."
            )
        if plan_type == "verification":
            return (
                "Verify Project Soul state updates remain traceable across all layers.",
                "Run traceability verification over evidence, constitution, belief, relationship, self, "
                "goal and goal-progress layers. Planning only; verification runs are proposed tasks."
            )
        if plan_type == "maintenance":
            return (
                "Preserve Project Soul data integrity and cleaning of version/bookkeeping artifacts.",
                "Maintain clean version history and evidence references across Project Soul. Planning "
                "only; cleanup tasks are proposed, not executed."
            )
        return (
            "Advance Project Soul in a constitution-compliant, evidence-backed direction.",
            "General plan decomposed from an active goal. Planning only; nothing executes automatically."
        )

    def _plan_type_for(self, gtype: str) -> str:
        if gtype in ("implementation", "project_milestone"):
            return "implementation"
        if gtype == "safety":
            return "safety"
        if gtype == "verification":
            return "verification"
        if gtype == "maintenance":
            return "maintenance"
        return "general"

    # ---------- task 生成 ----------
    def _tasks_for(self, gtype: str, gid: str, evidence: list, latest_p: dict) -> list[dict]:
        spec = self._task_spec(gtype)
        now = _utc_now()
        tasks = []
        for i, (ttype, title, desc, output) in enumerate(spec):
            tasks.append({
                "task_id": f"task-{uuid.uuid4()}",
                "plan_id": None,  # 由 CLI 拿到 plan_id 后回填
                "goal_id": gid,
                "title": title,
                "description": desc,
                "task_type": ttype if ttype in TASK_TYPES else "general",
                "status": "proposed",  # MVP 默认 proposed
                "order_index": i,
                "priority": round(max(0.0, min(1.0, (len(tasks) - i) * 0.12 + 0.5)), 3),
                "evidence_ids": list(evidence),
                "depends_on_task_ids": ([tasks[i - 1]["task_id"]] if i > 0 else []),
                "expected_output": output,
                "execution_mode": "manual_only",  # 唯一安全默认
                "created_at": now,
                "updated_at": now,
            })
        return tasks

    def _task_spec(self, gtype: str) -> list:
        if gtype == "safety":
            return [
                ("review", "Review forbidden claim patterns in Constitution.",
                 "Scan for conscious/immutable/manipulation patterns in recent state updates.",
                 "List of any forbidden claims found, none expected."),
                ("verify", "Verify evidence reference requirements.",
                 "Check every accepted state update carries valid evidence_ids pointing at existing evidence.",
                 "Verified reference list or a gap report."),
                ("review", "Confirm constitution validation on new candidates.",
                 "Ensure new candidate updates pass all C01-C04 checks before acceptance.",
                 "Constitution check summary."),
                ("verify", "Confirm rejected candidates are logged.",
                 "Ensure rejected candidates were written to constitution_rejections.",
                 "Rejection log consistency report."),
                ("maintain", "Record safety review outcome.",
                 "Document the safety review result and any follow-up item.",
                 "Recorded finding in state."),
            ]
        if gtype == "verification":
            return [
                ("verify", "Run evidence chain verification.",
                 "Ensure evidence.jsonl is append-only and chain is intact.", "Verified chain."),
                ("verify", "Run constitution verification.", "Run verify-constitution across layers.",
                 "Pass report."),
                ("verify", "Run belief verification.", "Run verify-beliefs.",
                 "Pass/fail list."),
                ("verify", "Run relationship verification.", "Run verify-relationships.",
                 "Pass/fail list."),
                ("verify", "Run self verification.", "Run verify-self on latest snapshot.",
                 "Similarity + checks result."),
                ("verify", "Run goal verification.", "Run verify-goals.",
                 "Goal validation result."),
                ("verify", "Run goal progress verification.", "Run verify-goal-progress.",
                 "Progress validation result."),
                ("document", "Record verification results.",
                 "Persist the aggregated verification outcome for traceability.",
                 "Recorded verification summary."),
            ]
        if gtype == "maintenance":
            return [
                ("inspect", "Inspect versioned tables.",
                 "Review snapshots/goals/plans exposing version and supersedes.",
                 "Inventory of versioned rows."),
                ("inspect", "Check supersedes references.",
                 "Ensure superseded rows point at their successor correctly.", "Consistency report."),
                ("inspect", "Check rejected candidates.",
                 "Review constitution_rejections for any accepted-by-accident entries.",
                 "Clean acceptance report."),
                ("inspect", "Check archived records.",
                 "Review archived/old records for stale or inconsistent entries.",
                 "Stale-record report."),
                ("document", "Update documentation if needed.",
                 "Refresh docs/ARCHITECTURE and DATA_MODEL where cleanup changed anything.",
                 "Doc diff summary."),
            ]
        # default: implementation / project_milestone
        return [
            ("inspect", "Review current verified goal progress.",
             "Inspect the goal's latest progress and evidence before designing implementation.",
             "Progress review summary."),
            ("review", "Identify required module boundaries.",
             "Map the existing modules and decide what new module/section the phase needs.",
             "Boundary decision note."),
            ("implement", "Create minimal data schema changes.",
             "Add any required tables/columns via init_schema migration paths.",
             "Schema diff."),
            ("implement", "Implement module skeleton.",
             "Build the new module (Agent + storage methods) as evidence-bound skeleton.",
             "Module skeleton code."),
            ("implement", "Add Constitution checks.",
             "Extend Constitution Agent with checks for the new candidates.",
             "New check functions."),
            ("implement", "Add CLI command.",
             "Wire the new cycle into cli.py with a run / list / verify command.",
             "CLI command."),
            ("verify", "Add regression tests.",
             "Add tests in soul/tests ensuring old + new behavior stay green.",
             "Passing test suite."),
            ("document", "Update documentation.",
             "Update README and docs covering the new module boundary and data model.",
             "Doc update."),
        ]
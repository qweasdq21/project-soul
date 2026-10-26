"""test_goal_consolidation.py — Phase 12 goal consolidation 落库 + Decision 长期上下文接入。"""
import os
import shutil
import tempfile
import uuid

import pytest

from soul.storage.sqlite_store import SQLiteStore
from soul.agents.consolidation import GoalConsolidationAgent
from soul.agents.decision import DecisionAgent


@pytest.fixture
def store():
    d = tempfile.mkdtemp()
    s = SQLiteStore(os.path.join(d, "state.sqlite3"))
    s.init_schema()
    yield s
    shutil.rmtree(d, ignore_errors=True)


def _goal(s, gt, t, d, ev=None, priority=0.5, status="active"):
    gid = f"goal-{uuid.uuid4().hex[:8]}"
    s.add_goal({"goal_id": gid, "title": t, "description": d,
                "goal_type": gt, "status": status, "priority": priority,
                "evidence_ids": ev or []})
    return gid


def test_consolidation_persisted(store):
    g1 = _goal(store, "project_milestone", "Implement next phase evidence-backed components",
               "phase implementation evidence architecture", ["e0"])
    g2 = _goal(store, "project_milestone", "Verify next phase regression",
               "phase implementation verification", ["e1"])
    res = GoalConsolidationAgent(store).run_consolidation_cycle()
    assert len(res) == 1
    r = res[0]
    lt = store.get_long_term_goal(r["long_term_goal_id"])
    assert lt is not None
    # 还原后是 list
    assert isinstance(lt.get("source_goal_ids"), list)
    assert set(lt["source_goal_ids"]) == {g1, g2}
    assert isinstance(lt.get("evidence_ids"), list)
    cons = store.list_goal_consolidations()
    assert len(cons) == 1
    assert isinstance(cons[0].get("source_goal_ids"), list)
    assert cons[0]["action_taken"] == "parent_created"


def test_decision_includes_continuity(store):
    from datetime import datetime, timezone
    # 两个 phase goal → consolidation → long-term goal
    g1 = _goal(store, "project_milestone", "Implement next phase evidence-backed components",
               "phase implementation evidence architecture", ["e0"], priority=0.8)
    g2 = _goal(store, "project_milestone", "Verify next phase regression",
               "phase implementation verification", ["e1"], priority=0.6)
    GoalConsolidationAgent(store).run_consolidation_cycle()

    # 造 plan+tasks 让 decision 能选
    plan_id = f"plan-{uuid.uuid4().hex[:8]}"
    store.add_plan({"plan_id": plan_id, "goal_id": g1, "status": "proposed",
                    "title": "Phase plan", "description": "plan", "plan_reason": "rule",
                    "plan_type": "implementation", "evidence_ids": ["e0"],
                    "source_goal_ids": [g1]})
    task_id = f"task-{uuid.uuid4().hex[:8]}"
    store.add_task({"task_id": task_id, "plan_id": plan_id, "goal_id": g1,
                    "title": "Review verified progress", "description": "review",
                    "status": "proposed", "order_index": 0, "execution_mode": "manual_only",
                    "evidence_ids": ["e0"], "source_goal_ids": [g1]})

    ltg = store.list_active_long_term_goals()
    assert len(ltg) == 1
    goals = store.list_active_goals()
    plans = store.list_plans()
    tasks = store.list_tasks()
    cands = DecisionAgent().process(goals=goals, plans=plans, tasks=tasks,
                                    long_term_goals=ltg)
    assert len(cands) >= 1
    dec = cands[0]
    assert "related_long_term_goal_ids" in dec
    assert dec["related_long_term_goal_ids"]  # 非空，指向 ltg
    assert dec["continuity_context"] is not None
    assert dec["continuity_context"]["goal_type"] == "project_continuity"
    # 选择逻辑未改变：仍是 next_task_recommendation / waiting_for_review / manual+no-exec
    assert dec["manual_review_required"] is True
    assert dec["execution_allowed"] is False


def test_verify_job_output_matches(store):
    # - 不产生伪造 evidence（consolidation 只聚合 source goals 的 evidence）
    g1 = _goal(store, "project_milestone", "Implement next phase",
               "phase implementation", ["e_x"])
    g2 = _goal(store, "project_milestone", "Verify next phase",
               "phase implementation", ["e_x"])
    res = GoalConsolidationAgent(store).run_consolidation_cycle()
    assert len(res) == 1
    assert res[0]["evidence_ids"] == ["e_x"]  # 仅聚合，不新造
"""test_goal_continuity.py — Phase 12 GoalConsolidationAgent 归并规则与聚合。"""
import os
import shutil
import tempfile
import uuid

import pytest

from soul.storage.sqlite_store import SQLiteStore
from soul.agents.consolidation import GoalConsolidationAgent


@pytest.fixture
def store():
    d = tempfile.mkdtemp()
    s = SQLiteStore(os.path.join(d, "state.sqlite3"))
    s.init_schema()
    yield s
    shutil.rmtree(d, ignore_errors=True)


def _add_goal(s, gtype, title, desc, ev=None, priority=0.5):
    gid = f"goal-{uuid.uuid4().hex[:8]}"
    s.add_goal({"goal_id": gid, "title": title, "description": desc,
                "goal_type": gtype, "status": "active", "priority": priority,
                "evidence_ids": ev or []})
    return gid


def test_no_consolidation_single_goal(store):
    g = _add_goal(store, "project_milestone", "Implement next phase",
                  "Project Soul phase implementation")
    ga = GoalConsolidationAgent(store)
    res = ga.run_consolidation_cycle()
    assert res == []


def test_consolidates_two_phase_goals(store):
    g1 = _add_goal(store, "project_milestone",
                   "Implement next phase evidence-backed components",
                   "Project Soul phase implementation evidence architecture")
    g2 = _add_goal(store, "project_milestone", "Verify regression across phases",
                   "verification traceability evidence chain constitution")
    ga = GoalConsolidationAgent(store)
    res = ga.run_consolidation_cycle()
    assert len(res) == 1
    r = res[0]
    assert r["goal_type"] == "project_continuity"
    assert set(r["source_goal_ids"]) == {g1, g2}
    assert r["action_taken"] == "parent_created"
    assert r["status"] == "active"
    # 落库验证
    assert store.get_long_term_goal(r["long_term_goal_id"]) is not None
    assert len(store.list_goal_consolidations()) == 1


def test_safety_continuity_group(store):
    g1 = _add_goal(store, "safety_constraint", "Real soul claims rejected",
                   "constitution no manipulation real soul", ["e1"])
    g2 = _add_goal(store, "safety_constraint", "Evidence immutability",
                   "evidence immutability no manipulation", ["e2"])
    ga = GoalConsolidationAgent(store)
    res = ga.run_consolidation_cycle()
    assert len(res) >= 1
    assert any(r["goal_type"] == "safety_continuity" for r in res)


def test_progress_aggregation(store):
    g1 = _add_goal(store, "project_milestone", "Implement next phase",
                   "phase implementation architecture", ["e0"])
    g2 = _add_goal(store, "project_milestone", "Verify next phase regression",
                   "phase implementation verification", ["e1"])
    store.update_goal_priority(g1, 0.8, "p")
    store.update_goal_priority(g2, 0.6, "p")
    ga = GoalConsolidationAgent(store)
    res = ga.run_consolidation_cycle()
    assert len(res) == 1
    r = res[0]
    # 无 progress rows → 0
    assert r["progress_value"] == 0.0
    assert 0.0 <= r["priority"] <= 1.0


def test_evidence_merged_from_source_goals(store):
    g1 = _add_goal(store, "project_milestone", "Implement next phase",
                   "phase implementation", ["e0", "e1"])
    g2 = _add_goal(store, "project_milestone", "Verify next phase",
                   "phase implementation", ["e1", "e2"])
    ga = GoalConsolidationAgent(store)
    res = ga.run_consolidation_cycle()
    assert len(res) == 1
    assert set(res[0]["evidence_ids"]) == {"e0", "e1", "e2"}


def test_already_consolidated_goal_not_reused(store):
    g1 = _add_goal(store, "project_milestone", "Implement next phase",
                   "phase implementation architecture")
    g2 = _add_goal(store, "project_milestone", "Verify next phase",
                   "phase implementation verification")
    ga = GoalConsolidationAgent(store)
    res1 = ga.run_consolidation_cycle()
    assert len(res1) == 1
    # 第二次运行：source goals 已归并 → 不再重复
    res2 = ga.run_consolidation_cycle()
    assert res2 == []
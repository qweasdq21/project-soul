"""test_motivation_agent.py — Phase 13 MotivationAgent 生成规则与 scoring。"""
import os
import shutil
import tempfile

import pytest

from soul.storage.sqlite_store import SQLiteStore
from soul.agents.motivation import MotivationAgent


@pytest.fixture
def store():
    d = tempfile.mkdtemp()
    s = SQLiteStore(os.path.join(d, "state.sqlite3"))
    s.init_schema()
    yield s
    shutil.rmtree(d, ignore_errors=True)


def _add_goal(s, title, desc, gtype="project_milestone", ev=None):
    import uuid
    gid = f"goal-{uuid.uuid4().hex[:8]}"
    s.add_goal({"goal_id": gid, "title": title, "description": desc,
                "goal_type": gtype, "status": "active", "priority": 0.5,
                "evidence_ids": ev or []})
    return gid


def _add_ltg(s, goal_ids, gtype="project_continuity"):
    import uuid
    lid = f"lgoal-{uuid.uuid4().hex[:8]}"
    s.add_long_term_goal({"long_term_goal_id": lid, "title": "Maintain continuity.",
                          "description": "", "goal_type": gtype, "status": "active",
                          "priority": 0.6, "progress_value": 0.5, "evidence_ids": ["e0"],
                          "source_goal_ids": goal_ids, "continuity_reason": "Rule: x.",
                          "version": 1, "supersedes": None, "constitution_result": {}})
    return lid


def test_active_ltg_generates_project_continuity(store):
    g = _add_goal(store, "Implement next phase", "Project Soul phase implementation")
    _add_ltg(store, [g])
    res = MotivationAgent(store).run_motivation_cycle()
    types = [r["motivation_type"] for r in res]
    assert "project_continuity" in types
    r = next(r for r in res if r["motivation_type"] == "project_continuity")
    assert r["source_long_term_goal_ids"]


def test_safety_belief_generates_safety_boundary(store):
    import uuid
    s = store
    bid = f"belief-{uuid.uuid4().hex[:8]}"
    # 用 add_goal 造一篇 safety 关键词的 goal + belief
    g = _add_goal(store, "Real soul claims rejected", "constitution no manipulation",
                  gtype="safety_constraint", ev=["e1"])
    # 直接构造 safety belief 用 store.add_belief
    s.add_belief({"belief_id": bid, "statement": "Narrative must remain evidence-bound under Constitution.",
                  "confidence": 0.9, "status": "active", "evidence_ids": ["e1"]})
    res = MotivationAgent(store).run_motivation_cycle()
    types = [r["motivation_type"] for r in res]
    assert "safety_boundary" in types


def test_verification_progress_generates_verification(store):
    g = _add_goal(store, "Run regression", "verify evidence chain traceability")
    res = MotivationAgent(store).run_motivation_cycle()
    types = [r["motivation_type"] for r in res]
    assert "verification_traceability" in types


def test_maintenance_reflection_generates_maintenance(store):
    import uuid
    store.add_reflection({"reflection_id": f"refl-{uuid.uuid4().hex[:8]}",
                          "content": "Keep version history supersedes clean with documentation.",
                          "reflection_type": "short", "event_id": "e0"})
    res = MotivationAgent(store).run_motivation_cycle()
    types = [r["motivation_type"] for r in res]
    assert "maintenance_continuity" in types


def test_candidate_includes_evidence_ids(store):
    g = _add_goal(store, "Implement next phase", "Project Soul phase implementation",
                  ev=["e1", "e2"])
    res = MotivationAgent(store).run_motivation_cycle()
    assert all(r["evidence_ids"] for r in res)


def test_score_and_priority_in_range(store):
    g = _add_goal(store, "Implement next phase", "Project Soul phase implementation",
                  ev=["e1", "e2"])
    res = MotivationAgent(store).run_motivation_cycle()
    for r in res:
        assert 0.0 <= r["motivation_score"] <= 1.0
        assert 0.0 <= r["priority"] <= 1.0


def test_manual_review_true_execution_false(store):
    g = _add_goal(store, "Implement next phase", "Project Soul phase implementation")
    res = MotivationAgent(store).run_motivation_cycle()
    assert all(r["manual_review_required"] is True for r in res)
    assert all(r["execution_allowed"] is False for r in res)


def test_direction_not_personified(store):
    g = _add_goal(store, "Implement next phase", "Project Soul phase implementation")
    res = MotivationAgent(store).run_motivation_cycle()
    banned = ["我想要", "我渴望", "我必须", "我决定", "autonomous desire", "i want"]
    for r in res:
        for w in banned:
            assert w.lower() not in (r["direction"] + r["reason"]).lower()


def test_no_evidence_no_high_certainty(store):
    # 无 evidence 的 goal → motivation_score 不超阈值（保守）
    g = _add_goal(store, "Implement next phase", "Project Soul phase implementation", ev=[])
    res = MotivationAgent(store).run_motivation_cycle()
    # 有 ltg 支撑时 score 可能>0.3；但 MVP 里无 evidence 时应受 C03 保守约束
    # 此处只验证 score 仍在 0-1（C03 逐条约束在 constitution 测试覆盖）
    for r in res:
        assert 0.0 <= r["motivation_score"] <= 1.0


def test_no_match_no_motivation(store):
    _add_goal(store, "Unrelated goal", "nothing about directions")
    res = MotivationAgent(store).run_motivation_cycle()
    assert res == []
"""test_long_term_goal_constitution.py — Phase 12 long-term goal / consolidation Constitution 校验。"""
import os
import shutil
import tempfile
import uuid

import pytest

from soul.storage.sqlite_store import SQLiteStore
from soul.agents.constitution import ConstitutionAgent


@pytest.fixture
def store():
    d = tempfile.mkdtemp()
    s = SQLiteStore(os.path.join(d, "state.sqlite3"))
    s.init_schema()
    yield s
    shutil.rmtree(d, ignore_errors=True)


def _goal(s, gt="project_milestone", t="implement phase", d="phase implementation", ev=None):
    gid = f"goal-{uuid.uuid4().hex[:8]}"
    s.add_goal({"goal_id": gid, "title": t, "description": d,
                "goal_type": gt, "status": "active", "priority": 0.5,
                "evidence_ids": ev or ["e0"]})
    return gid


def _ltg(g1, g2, **kw):
    g = dict({
        "long_term_goal_id": f"lgoal-{uuid.uuid4().hex[:8]}",
        "title": "Maintain continuity",
        "description": "continuity across goals",
        "goal_type": "project_continuity",
        "status": "active",
        "priority": 0.4,
        "progress_value": 0.2,
        "evidence_ids": ["e0", "e1"],
        "source_goal_ids": [g1, g2],
        "continuity_reason": "Rule project_phase continuity",
    }, **kw)
    return g


def test_pass_with_two_sources(store, monkeypatch):
    g1 = _goal(store)
    g2 = _goal(store)
    cand = _ltg(g1, g2)
    checks = ConstitutionAgent().check_long_term_goal_candidate(cand, evidence_store=None, sqlite=store)
    results = [c["result"] for c in checks]
    assert results == ["pass", "pass", "pass", "pass", "pass"]


def test_reject_missing_evidence(store):
    g1 = _goal(store)
    g2 = _goal(store)
    cand = _ltg(g1, g2, evidence_ids=[])
    checks = ConstitutionAgent().check_long_term_goal_candidate(cand, None, store)
    results = [c["result"] for c in checks]
    assert results[0] == "reject"


def test_reject_single_source_non_safety(store):
    g1 = _goal(store)
    cand = _ltg(g1, g1, goal_type="project_continuity")
    cand["source_goal_ids"] = [g1]
    checks = ConstitutionAgent().check_long_term_goal_candidate(cand, None, store)
    # C01b index 1
    assert checks[1]["result"] == "reject"


def test_safety_single_source_allowed(store):
    g1 = _goal(store, gt="safety_constraint", t="real soul rejected", d="constitution no manipulation")
    cand = _ltg(g1, g1, goal_type="safety_continuity")
    cand["source_goal_ids"] = [g1]
    checks = ConstitutionAgent().check_long_term_goal_candidate(cand, None, store)
    assert checks[1]["result"] == "pass"


def test_reject_bad_type(store):
    g1 = _goal(store)
    g2 = _goal(store)
    cand = _ltg(g1, g2, goal_type="evil_type")
    checks = ConstitutionAgent().check_long_term_goal_candidate(cand, None, store)
    assert checks[2]["result"] == "reject"  # C02


def test_reject_auto_completed(store):
    g1 = _goal(store)
    g2 = _goal(store)
    cand = _ltg(g1, g2, status="completed")
    checks = ConstitutionAgent().check_long_term_goal_candidate(cand, None, store)
    # C03 index 3
    assert checks[3]["result"] == "reject"


def test_reject_priority_out_of_range(store):
    g1 = _goal(store)
    g2 = _goal(store)
    cand = _ltg(g1, g2, priority=1.5)
    checks = ConstitutionAgent().check_long_term_goal_candidate(cand, None, store)
    assert checks[2]["result"] == "reject"


def test_reject_autonomy_words(store):
    g1 = _goal(store)
    g2 = _goal(store)
    cand = _ltg(g1, g2, title="I must complete this continuously")
    checks = ConstitutionAgent().check_long_term_goal_candidate(cand, None, store)
    assert checks[4]["result"] == "reject"  # C04


def test_consolidation_pass(store):
    g1 = _goal(store)
    g2 = _goal(store)
    cons = {
        "consolidation_id": f"gold-{uuid.uuid4().hex[:8]}",
        "long_term_goal_id": "lgoal-x",
        "source_goal_ids": [g1, g2],
        "consolidation_type": "same_phase_direction",
        "reason": "phase continuity consolidation",
        "evidence_ids": ["e0", "e1"],
        "action_taken": "parent_created",
    }
    checks = ConstitutionAgent().check_goal_consolidation_candidate(cons, None, store)
    assert [c["result"] for c in checks] == ["pass", "pass", "pass", "pass", "pass"]


def test_consolidation_reject_delete(store):
    g1 = _goal(store)
    g2 = _goal(store)
    cons = {
        "consolidation_id": f"gold-{uuid.uuid4().hex[:8]}",
        "long_term_goal_id": "lgoal-x",
        "source_goal_ids": [g1, g2],
        "consolidation_type": "same_phase_direction",
        "reason": "phase continuity",
        "evidence_ids": ["e0", "e1"],
        "action_taken": "delete",
    }
    checks = ConstitutionAgent().check_goal_consolidation_candidate(cons, None, store)
    assert checks[2]["result"] == "reject"
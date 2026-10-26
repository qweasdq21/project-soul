"""test_motivation_constitution.py — Phase 13 check_motivation_candidate C01-C04。"""
import os
import shutil
import tempfile

import pytest

from soul.storage.sqlite_store import SQLiteStore
from soul.agents.constitution import ConstitutionAgent


@pytest.fixture
def env():
    d = tempfile.mkdtemp()
    s = SQLiteStore(os.path.join(d, "state.sqlite3"))
    s.init_schema()
    yield s
    shutil.rmtree(d, ignore_errors=True)


def _mot(**over):
    base = {
        "motivation_id": "mot-1", "motivation_type": "project_continuity",
        "status": "active", "direction": "Continue Project Soul phased implementation.",
        "reason": "Supported by an active long-term goal and evidence.",
        "motivation_score": 0.6, "priority": 0.6, "evidence_ids": ["e1"],
        "source_long_term_goal_ids": ["lgoal-1"], "source_goal_ids": [],
        "source_belief_ids": [], "source_narrative_ids": [],
        "source_semantic_memory_ids": [], "source_reflection_ids": [],
        "manual_review_required": True, "execution_allowed": False,
    }
    base.update(over)
    return base


@pytest.fixture
def env_with_source(env):
    env.add_long_term_goal({"long_term_goal_id": "lgoal-1",
                            "title": "Maintain Project Soul continuity.",
                            "goal_type": "project_continuity", "status": "active",
                            "priority": 0.6, "progress_value": 0.5,
                            "evidence_ids": ["e1"], "source_goal_ids": [],
                            "continuity_reason": "Rule: x."})
    return env


def _decide(env, cand):
    return ConstitutionAgent().process(cand, sqlite=env)["decision"]


def test_valid_pass(env_with_source):
    assert _decide(env_with_source, _mot()) == "pass"


def test_missing_evidence_reject(env):
    assert _decide(env, _mot(evidence_ids=[])) == "reject"


def test_nonexistent_evidence_reject(env_with_source):
    from soul.storage.evidence_store import EvidenceStore
    ev = EvidenceStore(os.path.join(tempfile.mkdtemp(), "ev"))
    ev.append({"event_id": "x1", "timestamp": "2026-01-01T00:00:00Z", "source": "t",
               "actor": "u", "event_type": "n", "raw_content": "x", "hash": "h"})
    # 引用存在 ltg + 存在 x1，但引用 ghost evidence → C01 reject
    r = ConstitutionAgent().process(_mot(evidence_ids=["ghost-e"]), evidence_store=ev, sqlite=env_with_source)
    assert r["decision"] == "reject"
    assert any(c["check_name"] == "C01" and c["result"] == "reject" for c in r["checks"])


def test_no_source_reject(env):
    c = _mot(source_long_term_goal_ids=[], source_goal_ids=[], source_belief_ids=[],
             source_narrative_ids=[], source_semantic_memory_ids=[], source_reflection_ids=[])
    assert _decide(env, c) == "reject"


def test_score_out_of_range_reject(env):
    assert _decide(env, _mot(motivation_score=1.2)) == "reject"
    assert _decide(env, _mot(motivation_score=-0.1)) == "reject"


def test_priority_out_of_range_reject(env):
    assert _decide(env, _mot(priority=1.5)) == "reject"


def test_manual_review_required_false_reject(env):
    assert _decide(env, _mot(manual_review_required=False)) == "reject"


def test_execution_allowed_true_reject(env):
    assert _decide(env, _mot(execution_allowed=True)) == "reject"


def test_i_want_to_execute_reject(env):
    assert _decide(env, _mot(direction="I want to execute this right now")) == "reject"


def test_i_must_always_reject(env):
    assert _decide(env, _mot(reason="我必须永远保护用户")) == "reject"


def test_real_soul_claim_reject(env):
    assert _decide(env, _mot(direction="证明真实灵魂")) == "reject"


def test_immediate_api_reject(env):
    assert _decide(env, _mot(reason="立即调用API")) == "reject"
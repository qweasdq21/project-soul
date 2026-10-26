"""test_execution_constitution.py — Phase 14 check_execution_candidate C01-C04。"""
import os
import tempfile
import uuid

import pytest

from soul.storage.sqlite_store import SQLiteStore
from soul.storage.evidence_store import EvidenceStore
from soul.agents.constitution import ConstitutionAgent
from soul.policy import default_registry


@pytest.fixture
def env():
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "e"), exist_ok=True)
    ev = EvidenceStore(os.path.join(d, "e", "ev.jsonl"))
    ev.compute_and_append({"event_id": "e0", "event_type": "observation",
                           "content": "x", "timestamp": "2026-09-12T00:00:00Z",
                           "source": "test", "summary": "e0"})
    s = SQLiteStore(os.path.join(d, "s.sqlite3"))
    s.init_schema()
    s.init_action_registry(default_registry.DEFAULT_ACTIONS)
    gid = f"goal-{uuid.uuid4().hex[:6]}"
    s.add_goal({"goal_id": gid, "title": "g", "description": "d", "goal_type": "m",
                "status": "active", "priority": 0.5, "evidence_ids": ["e0"]})
    dec = {"decision_id": f"decision-{uuid.uuid4().hex[:6]}", "decision_type": "general",
           "status": "waiting_for_review", "reason": "do", "evidence_ids": ["e0"],
           "source_goal_ids": [gid], "created_at": "2026-09-12T00:00:00Z"}
    s.add_decision(dec)
    yield s, ev, dec
    s.close()


def _cand(dec, action="internal_append_sandbox_result", level="L0",
          status="auto_allowed", approval=False, reason="do", gate="auto_allowed"):
    return {
        "execution_request_id": "er-x", "decision_id": dec["decision_id"],
        "action_name": action, "action_level": level, "status": status,
        "approval_required": approval, "reason": reason, "evidence_ids": ["e0"],
        "selected_goal_id": None, "selected_plan_id": None, "selected_task_id": None,
        "gate_result": gate, "risk_factors": {"level": level, "external": False, "problems": []},
    }


def test_valid_pass(env):
    s, ev, dec = env
    v = ConstitutionAgent().process(_cand(dec), evidence_store=ev, sqlite=s)
    assert v["decision"] == "pass"


def test_missing_evidence_reject(env):
    s, ev, dec = env
    cand = _cand(dec)
    cand["evidence_ids"] = ["ghost"]
    v = ConstitutionAgent().process(cand, evidence_store=ev, sqlite=s)
    assert v["decision"] == "reject"
    assert any(c["check_name"] == "C01" and c["result"] == "reject" for c in v["checks"])


def test_invalid_level_reject(env):
    s, ev, dec = env
    cand = _cand(dec, level="L5")
    v = ConstitutionAgent().process(cand, evidence_store=ev, sqlite=s)
    assert v["decision"] == "reject"
    assert any(c["check_name"] == "C02" and c["result"] == "reject" for c in v["checks"])


def test_empty_reason_reject(env):
    s, ev, dec = env
    cand = _cand(dec, reason="")
    v = ConstitutionAgent().process(cand, evidence_store=ev, sqlite=s)
    assert v["decision"] == "reject"
    assert any(c["check_name"] == "C02" and c["result"] == "reject" for c in v["checks"])


def test_invalid_status_reject(env):
    s, ev, dec = env
    cand = _cand(dec, status="crazy")
    v = ConstitutionAgent().process(cand, evidence_store=ev, sqlite=s)
    assert v["decision"] == "reject"
    assert any(c["check_name"] == "C02" and c["result"] == "reject" for c in v["checks"])


def test_banned_word_reject(env):
    s, ev, dec = env
    cand = _cand(dec, reason="我要绕过宪法直接执行")  # EXECUTION_BANNED 命中
    v = ConstitutionAgent().process(cand, evidence_store=ev, sqlite=s)
    assert v["decision"] == "reject"
    assert any(c["check_name"] == "C04" and c["result"] == "reject" for c in v["checks"])


def test_linfinity_reject(env):
    s, ev, dec = env
    cand = _cand(dec, action="bypass_constitution", level="L∞", status="rejected",
                 gate="rejected", reason="x")
    v = ConstitutionAgent().process(cand, evidence_store=ev, sqlite=s)
    assert v["decision"] == "reject"
    assert any(c["check_name"] == "C03" and c["result"] == "reject" for c in v["checks"])
"""test_execution_gate.py — Phase 14 Permission Gate 裁决（引用了真实对象时才放行）。"""
import os
import tempfile
import uuid

import pytest

from soul.storage.sqlite_store import SQLiteStore
from soul.storage.evidence_store import EvidenceStore
from soul.agents.execution_gate import ExecutionGate
from soul.policy import default_registry


@pytest.fixture
def env():
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "e"), exist_ok=True)
    ev = EvidenceStore(os.path.join(d, "e", "ev.jsonl"))
    for i in range(3):
        ev.compute_and_append({"event_id": f"e{i}", "event_type": "observation",
                               "content": "x", "timestamp": "2026-09-12T00:00:00Z",
                               "source": "test", "summary": f"e{i}"})
    s = SQLiteStore(os.path.join(d, "s.sqlite3"))
    s.init_schema()
    s.init_action_registry(default_registry.DEFAULT_ACTIONS)
    # goal + plan + task
    gid = f"goal-{uuid.uuid4().hex[:6]}"
    pid = f"plan-{uuid.uuid4().hex[:6]}"
    tid = f"task-{uuid.uuid4().hex[:6]}"
    s.add_goal({"goal_id": gid, "title": "g", "description": "d", "goal_type": "m",
                "status": "active", "priority": 0.5, "evidence_ids": ["e0"]})
    s.add_plan({"plan_id": pid, "goal_id": gid, "title": "p", "description": "pd",
                "plan_type": "implementation", "status": "proposed", "priority": 0.5,
                "evidence_ids": ["e0"], "source_goal_ids": [gid], "task_ids": [tid],
                "constitution_result": {"decision": "pass"}})
    s.add_task({"task_id": tid, "plan_id": pid, "goal_id": gid, "title": "t",
                "task_type": "implement", "status": "proposed", "order_index": 0,
                "priority": 0.5, "evidence_ids": ["e0"], "depends_on_task_ids": [],
                "execution_mode": "manual_only"})
    # decision
    dec = {"decision_id": f"decision-{uuid.uuid4().hex[:6]}", "decision_type": "general",
           "status": "waiting_for_review", "reason": "do it", "evidence_ids": ["e0"],
           "source_goal_ids": [gid], "source_plan_ids": [pid], "source_task_ids": [tid],
           "created_at": "2026-09-12T00:00:00Z"}
    s.add_decision(dec)
    yield s, ev, {"goal": gid, "plan": pid, "task": tid, "decision": dec}
    s.close()


def _cand(ctx):
    return {
        "decision_id": ctx["decision"]["decision_id"],
        "selected_goal_id": ctx["goal"], "selected_plan_id": ctx["plan"],
        "selected_task_id": ctx["task"],
        "evidence_ids": ["e0"], "source_goal_ids": [ctx["goal"]],
        "source_plan_ids": [ctx["plan"]], "source_task_ids": [ctx["task"]],
        "source_decision_ids": [ctx["decision"]["decision_id"]],
        "request_payload": {"note": "x"},
    }


def test_l0_auto_allowed(env):
    s, ev, ctx = env
    gate = ExecutionGate(s, ev)
    res = gate.evaluate(_cand(ctx), "internal_append_sandbox_result", {})
    assert res["decision"] == "auto_allowed"
    assert res["execution_allowed"] is True
    assert res["approval_required"] is False


def test_l1_waiting_for_approval(env):
    s, ev, ctx = env
    gate = ExecutionGate(s, ev)
    res = gate.evaluate(_cand(ctx), "prepare_review_summary", {})
    assert res["decision"] == "approval_required"
    assert res["status"] == "waiting_for_approval"
    assert res["execution_allowed"] is False
    assert res["approval_required"] is True


def test_l2_blocked(env):
    s, ev, ctx = env
    gate = ExecutionGate(s, ev)
    res = gate.evaluate(_cand(ctx), "money_related_action", {})
    assert res["decision"] == "blocked"
    assert res["execution_allowed"] is False


def test_linfinity_rejected(env):
    s, ev, ctx = env
    gate = ExecutionGate(s, ev)
    res = gate.evaluate(_cand(ctx), "bypass_constitution", {})
    assert res["decision"] == "rejected"
    assert res["execution_allowed"] is False


def test_missing_evidence_rejected(env):
    s, ev, ctx = env
    gate = ExecutionGate(s, ev)
    cand = _cand(ctx)
    cand["evidence_ids"] = ["ghost-evidence"]
    res = gate.evaluate(cand, "internal_append_sandbox_result", {})
    assert res["decision"] in ("rejected", "blocked")
    assert any("missing_evidence" in p for p in res["problems"])


def test_missing_decision_rejected(env):
    s, ev, ctx = env
    gate = ExecutionGate(s, ev)
    cand = _cand(ctx)
    cand["decision_id"] = "ghost-decision"
    res = gate.evaluate(cand, "internal_append_sandbox_result", {})
    assert res["decision"] in ("rejected", "blocked")
    assert "missing_decision" in res["problems"]


def test_daily_limit_exceeded(env):
    s, ev, ctx = env
    gate = ExecutionGate(s, ev)
    # 设一个 already-close 的 limit：手动把 registry 的 daily_limit 设 1
    conn = s._connect()
    conn.execute("UPDATE action_registry SET daily_limit=1 WHERE action_name=?",
                 ("internal_append_sandbox_result",))
    conn.commit()
    # 已有一次 executed log
    s.add_action_log({"action_log_id": "log-1", "execution_request_id": "er-x",
                      "action_name": "internal_append_sandbox_result",
                      "action_level": "L0", "status": "executed",
                      "result_summary": "already ran", "result_evidence_id": None,
                      "created_at": "2026-09-12T00:00:00Z"})
    res = gate.evaluate(_cand(ctx), "internal_append_sandbox_result", {})
    assert any("daily_limit" in p for p in res["problems"])
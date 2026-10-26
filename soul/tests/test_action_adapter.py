"""test_action_adapter.py — Phase 14 Sandbox 动作执行：写 log + 回写 evidence + 不改 status。"""
import os
import tempfile
import uuid

import pytest

from soul.storage.sqlite_store import SQLiteStore
from soul.storage.evidence_store import EvidenceStore
from soul.agents.action_adapter import ActionAdapter
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
    # goal/plan/task to ensure status immutability check
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
    dec = {"decision_id": f"decision-{uuid.uuid4().hex[:6]}", "decision_type": "general",
           "status": "waiting_for_review", "reason": "do", "evidence_ids": ["e0"],
           "source_goal_ids": [gid], "source_plan_ids": [pid], "source_task_ids": [tid],
           "created_at": "2026-09-12T00:00:00Z"}
    s.add_decision(dec)
    yield s, ev
    s.close()


def _er(s, gid, pid, tid, decision_id, action="internal_append_sandbox_result", status="auto_allowed"):
    er_id = f"er-{uuid.uuid4().hex[:6]}"
    s.add_execution_request({
        "execution_request_id": er_id, "decision_id": decision_id,
        "selected_goal_id": gid, "selected_plan_id": pid, "selected_task_id": tid,
        "action_name": action, "action_level": "L0", "status": status,
        "approval_required": False, "manual_review_required": True,
        "execution_allowed": True, "reason": "do", "request_payload": {"note": "x"},
        "evidence_ids": ["e0"], "source_goal_ids": [gid], "source_plan_ids": [pid],
        "source_task_ids": [tid], "source_decision_ids": [decision_id],
        "risk_factors": {}, "gate_result": {"decision": "auto_allowed"},
    })
    return er_id


def test_l0_sandbox_action_executes(env):
    s, ev = env
    gid = s.list_goals()[0]["goal_id"]
    pid = s.list_plans()[0]["plan_id"]
    tid = s.list_tasks()[0]["task_id"]
    decision_id = s.list_decisions()[0]["decision_id"]
    er_id = _er(s, gid, pid, tid, decision_id)
    er = s.get_execution_request(er_id)
    before_g, before_p, before_t = (s.get_goal(gid)["status"], s.get_plan(pid)["status"],
                                    s.get_task(tid)["status"])
    adapter = ActionAdapter(s, ev)
    res = adapter.run(er, {"note": "hello"})
    assert res.status == "success"
    # 写 action_log
    logs = s.list_action_logs()
    assert len(logs) == 1
    # 回写 evidence
    assert res.result_evidence_id is not None
    ev_after = {e["event_id"] for e in ev.list_all()}
    assert res.result_evidence_id in ev_after
    # verify chain 仍有效
    valid, _ = ev.verify_chain()
    assert valid
    # 不改 goal/plan/task status
    assert s.get_goal(gid)["status"] == before_g
    assert s.get_plan(pid)["status"] == before_p
    assert s.get_task(tid)["status"] == before_t


def test_all_sandbox_actions(env):
    s, ev = env
    gid = s.list_goals()[0]["goal_id"]
    pid = s.list_plans()[0]["plan_id"]
    tid = s.list_tasks()[0]["task_id"]
    decision_id = s.list_decisions()[0]["decision_id"]
    for action in ("internal_record_review_note", "internal_create_checklist_snapshot",
                   "internal_run_readonly_verification", "internal_append_sandbox_result"):
        er_id = _er(s, gid, pid, tid, decision_id, action=action)
        res = ActionAdapter(s, ev).run(s.get_execution_request(er_id), {"note": "n"})
        assert res.status == "success", f"{action} failed"


def test_failure_writes_log(env):
    s, ev = env
    gid = s.list_goals()[0]["goal_id"]
    pid = s.list_plans()[0]["plan_id"]
    tid = s.list_tasks()[0]["task_id"]
    decision_id = s.list_decisions()[0]["decision_id"]
    er_id = _er(s, gid, pid, tid, decision_id, action="not_a_handler")
    res = ActionAdapter(s, ev).run(s.get_execution_request(er_id), {})
    assert res.status == "failed"
    logs = s.list_action_logs()
    assert len(logs) == 1
    assert logs[0]["status"] == "failed"
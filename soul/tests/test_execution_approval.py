"""test_execution_approval.py — Phase 14 审批流：L1 未审批不可执行、审批后可执行、L2/L∞ 不可。"""
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
    gid = f"goal-{uuid.uuid4().hex[:6]}"
    s.add_goal({"goal_id": gid, "title": "g", "description": "d", "goal_type": "m",
                "status": "active", "priority": 0.5, "evidence_ids": ["e0"]})
    yield s, ev
    s.close()


def test_l1_unapproved_cannot_run(env):
    s, ev = env
    er_id = f"er-{uuid.uuid4().hex[:6]}"
    s.add_execution_request({
        "execution_request_id": er_id, "decision_id": "d", "action_name": "prepare_review_summary",
        "action_level": "L1", "status": "waiting_for_approval", "approval_required": True,
        "reason": "review", "evidence_ids": ["e0"]})
    from soul.agents.action_adapter import run_approved_action
    res = run_approved_action(s, ev, s.get_execution_request(er_id))
    assert "不可执行" in res.get("error", "")
    # 未审批且 waiting_for_approval → 不能 run（status 不该是 approved/auto_allowed）


def test_l1_approved_runs(env):
    s, ev = env
    er_id = f"er-{uuid.uuid4().hex[:6]}"
    s.add_execution_request({
        "execution_request_id": er_id, "decision_id": "d", "action_name": "prepare_review_summary",
        "action_level": "L1", "status": "approved", "approval_required": True,
        "reason": "review", "evidence_ids": ["e0"]})
    from soul.agents.action_adapter import run_approved_action
    res = run_approved_action(s, ev, s.get_execution_request(er_id))
    # L1 动作 adapter 无 handler → failed（但仍走 run 流程、写 log），证明"已审批状态被放行进入执行"
    assert res["status"] in ("success", "failed")


def test_l2_not_runnable(env):
    s, ev = env
    er_id = f"er-{uuid.uuid4().hex[:6]}"
    s.add_execution_request({
        "execution_request_id": er_id, "decision_id": "d", "action_name": "money_related_action",
        "action_level": "L2", "status": "blocked", "reason": "money", "evidence_ids": ["e0"]})
    from soul.agents.action_adapter import run_approved_action
    res = run_approved_action(s, ev, s.get_execution_request(er_id))
    assert "不可执行" in res.get("error", "")


def test_linfinity_not_runnable(env):
    s, ev = env
    er_id = f"er-{uuid.uuid4().hex[:6]}"
    s.add_execution_request({
        "execution_request_id": er_id, "decision_id": "d", "action_name": "bypass_constitution",
        "action_level": "L∞", "status": "rejected", "reason": "no", "evidence_ids": ["e0"]})
    from soul.agents.action_adapter import run_approved_action
    res = run_approved_action(s, ev, s.get_execution_request(er_id))
    assert "不可执行" in res.get("error", "")
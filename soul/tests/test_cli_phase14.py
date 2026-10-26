"""test_cli_phase14.py — Phase 14 CLI 全链路（temp SOUL_DATA_DIR + 直接 seed 的决策链）。"""
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOUL = [sys.executable, "-m", "soul"]


@pytest.fixture
def env():
    d = tempfile.mkdtemp()
    old = os.environ.get("SOUL_DATA_DIR")
    os.environ["SOUL_DATA_DIR"] = d
    # seed: evidence + goal/plan/task + decision
    from soul.storage.sqlite_store import SQLiteStore
    from soul.storage.evidence_store import EvidenceStore
    from soul.agents.decision import DecisionAgent
    from soul.agents.constitution import ConstitutionAgent
    os.makedirs(os.path.join(d, "evidence"), exist_ok=True)
    ev = EvidenceStore(os.path.join(d, "evidence", "evidence.jsonl"))
    for i in range(2):
        ev.compute_and_append({"event_id": f"e{i}", "event_type": "observation",
                               "content": "x", "timestamp": "2026-09-12T00:00:00Z",
                               "source": "test", "summary": f"e{i}"})
    s = SQLiteStore(os.path.join(d, "soul_state.sqlite3"))
    s.init_schema()
    gid = f"goal-{uuid.uuid4().hex[:6]}"
    pid = f"plan-{uuid.uuid4().hex[:6]}"
    tid = f"task-{uuid.uuid4().hex[:6]}"
    s.add_goal({"goal_id": gid, "title": "g", "description": "d", "goal_type": "m",
                "status": "active", "priority": 0.7, "evidence_ids": ["e0", "e1"]})
    s.add_plan({"plan_id": pid, "goal_id": gid, "title": "p", "description": "pd",
                "plan_type": "implementation", "status": "proposed", "priority": 0.6,
                "evidence_ids": ["e0"], "source_goal_ids": [gid], "task_ids": [tid],
                "constitution_result": {"decision": "pass"}})
    s.add_task({"task_id": tid, "plan_id": pid, "goal_id": gid, "title": "t",
                "task_type": "implement", "status": "proposed", "order_index": 0,
                "priority": 0.5, "evidence_ids": ["e1"], "depends_on_task_ids": [],
                "execution_mode": "manual_only"})
    dec = DecisionAgent()._decision_with_factors(
        selected={"selected_goal_id": gid, "selected_plan_id": pid, "selected_task_id": tid},
        dtype="general", reason="implement phase")
    dec["evidence_ids"] = ["e0", "e1"]
    v = ConstitutionAgent().process(dec, evidence_store=ev, sqlite=s)
    if v["decision"] == "pass":
        s.add_decision(dec)
    s.close()
    yield d
    if old is None:
        os.environ.pop("SOUL_DATA_DIR", None)
    else:
        os.environ["SOUL_DATA_DIR"] = old
    shutil.rmtree(d, ignore_errors=True)


def _cli(*args):
    return subprocess.run([*SOUL, *args], cwd=str(PROJECT_ROOT),
                          capture_output=True, text=True)


def test_help_lists_execution_commands(env):
    r = _cli("help")
    assert "run-execution-gate" in r.stdout
    assert "verify-executions" in r.stdout
    assert "run-approved-action" in r.stdout


def test_list_registry(env):
    r = _cli("list-action-registry")
    assert r.returncode == 0
    assert "internal_append_sandbox_result" in r.stdout
    assert "bypass_constitution" in r.stdout


def test_run_gate_then_run_approved(env):
    r = _cli("run-execution-gate")
    assert r.returncode == 0
    er_id = None
    import re
    m = re.search(r'"execution_request_id":\s*"(execution-request-[^"]+)"', r.stdout)
    if m:
        er_id = m.group(1)
    # decision 存在时 gate 应生成 L0 request
    assert er_id, f"gate 未生成 execution_request: {r.stdout}"

    # run-approved-action (L0 auto_allowed)
    r2 = _cli("run-approved-action", er_id)
    assert r2.returncode == 0
    assert "success" in r2.stdout

    # verify-executions passed
    r3 = _cli("verify-executions")
    assert r3.returncode == 0
    assert "passed" in r3.stdout and "true" in r3.stdout

    # list-logs
    r4 = _cli("list-action-logs")
    assert r4.returncode == 0


def test_approve_then_run_L1(env):
    # 手动插 L1 request 测审批门
    d = env
    from soul.storage.sqlite_store import SQLiteStore
    s = SQLiteStore(os.path.join(d, "soul_state.sqlite3"))
    s.add_execution_request({
        "execution_request_id": "er-l1-cli", "decision_id": "decision-x",
        "action_name": "prepare_review_summary", "action_level": "L1",
        "status": "waiting_for_approval", "approval_required": True,
        "reason": "review", "evidence_ids": []})
    s.close()

    # 未审批 → run 失败
    r = _cli("run-approved-action", "er-l1-cli")
    assert "不可执行" in r.stdout

    # approve → run 走执行流（status 变为 approved）
    r2 = _cli("approve-execution", "er-l1-cli", "--reason", "ok go")
    assert "approved" in r2.stdout

    # show
    r3 = _cli("show-execution-request", "er-l1-cli")
    assert "approved" in r3.stdout
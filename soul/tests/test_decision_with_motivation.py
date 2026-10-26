"""test_decision_with_motivation.py — Phase 13 Decision 只读读取 motivation context。

验证：run-motivation-cycle 后 run-decision-cycle，decision trace 可含 related_motivation_ids；
decision 仍只选 existing task、不新建 task、execution_allowed=false；motivation 不改任何状态。
"""
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
    yield d
    if old is None:
        os.environ.pop("SOUL_DATA_DIR", None)
    else:
        os.environ["SOUL_DATA_DIR"] = old
    shutil.rmtree(d, ignore_errors=True)


def _seed(env_dir):
    from soul.storage.sqlite_store import SQLiteStore
    from soul.storage.evidence_store import EvidenceStore
    ev_dir = os.path.join(env_dir, "evidence")
    os.makedirs(ev_dir, exist_ok=True)
    ev = EvidenceStore(os.path.join(ev_dir, "evidence.jsonl"))
    for i in range(3):
        ev.compute_and_append({"event_id": f"e{i}", "event_type": "observation",
                               "content": "phase observation", "timestamp": "2026-09-12T00:00:00Z",
                               "source": "test", "summary": f"phase {i}"})
    s = SQLiteStore(os.path.join(env_dir, "soul_state.sqlite3"))
    s.init_schema()
    gid = f"goal-{uuid.uuid4().hex[:8]}"
    s.add_goal({"goal_id": gid, "title": "Implement next phase evidence-backed",
                "description": "Project Soul phase implementation architecture",
                "goal_type": "project_milestone", "status": "active", "priority": 0.7,
                "evidence_ids": ["e0", "e1"]})
    pid = f"plan-{uuid.uuid4().hex[:8]}"
    tid = f"task-{uuid.uuid4().hex[:8]}"
    s.add_plan({"plan_id": pid, "goal_id": gid, "title": "Build phase", "description": "impl",
                "plan_type": "implementation", "status": "proposed", "priority": 0.6,
                "evidence_ids": ["e0"], "source_goal_ids": [gid], "task_ids": [tid],
                "constitution_result": {"decision": "pass"}})
    s.add_task({"task_id": tid, "plan_id": pid, "goal_id": gid, "title": "Implement module",
                "task_type": "implement", "status": "proposed", "order_index": 0,
                "priority": 0.5, "evidence_ids": ["e1"],
                "depends_on_task_ids": [], "execution_mode": "manual_only"})
    lid = f"lgoal-{uuid.uuid4().hex[:8]}"
    s.add_long_term_goal({"long_term_goal_id": lid,
                          "title": "Maintain Project Soul phased implementation continuity.",
                          "goal_type": "project_continuity", "status": "active",
                          "priority": 0.6, "progress_value": 0.5,
                          "evidence_ids": ["e0", "e1"], "source_goal_ids": [gid],
                          "continuity_reason": "Rule: project_phase."})
    return gid, pid, tid, lid


def _run(*args):
    r = subprocess.run([*SOUL, *args], cwd=str(PROJECT_ROOT),
                       capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def test_decision_after_motivation_contains_related_mot(env):
    gid, pid, tid, lid = _seed(env)
    rc, out, _ = _run("run-motivation-cycle")
    assert rc == 0
    # motivation 应引用 goal/long-term goal
    assert "mot-" in out
    rc, out, err = _run("run-decision-cycle")
    assert rc == 0, err
    import json
    trace = json.loads(out)
    # decision 关联了 motivation（goal 命中同一 project_continuity 方向）
    assert trace["related_motivation_ids"], "decision 应含 related_motivation_ids"
    # decision 仍只选 existing task、不新建
    assert trace["selected_task_id"] == tid
    assert trace["execution_allowed"] is False
    assert trace["manual_review_required"] is True


def test_decision_still_selects_existing_task_only(env):
    gid, pid, tid, lid = _seed(env)
    _run("run-motivation-cycle")
    rc, out, err = _run("run-decision-cycle")
    assert rc == 0, err
    import json
    trace = json.loads(out)
    assert trace["selected_task_id"] == tid  # 正是 seed 的那一个 existing task
    assert trace["selected_task_title"] == "Implement module"


def test_decision_not_creating_task(env):
    from soul.storage.sqlite_store import SQLiteStore
    gid, pid, tid, lid = _seed(env)
    _run("run-motivation-cycle")
    _run("run-decision-cycle")
    s = SQLiteStore(os.path.join(env, "soul_state.sqlite3"))
    s.init_schema()
    # 仍只有 seed 的 1 个 task，decision 没新建
    assert len(s.list_tasks()) == 1
    assert len(s.list_plans()) == 1


def test_decision_execution_allowed_false(env):
    gid, pid, tid, lid = _seed(env)
    _run("run-motivation-cycle")
    rc, out, _ = _run("run-decision-cycle")
    assert rc == 0
    import json
    trace = json.loads(out)
    assert trace["execution_allowed"] is False


def test_motivation_not_changing_status(env):
    from soul.storage.sqlite_store import SQLiteStore
    gid, pid, tid, lid = _seed(env)
    rc, out, _ = _run("run-motivation-cycle")
    assert rc == 0
    s = SQLiteStore(os.path.join(env, "soul_state.sqlite3"))
    s.init_schema()
    # motivation 之后：goal/plan/task 状态不变
    g = s.get_goal(gid)
    p = s.get_plan(pid) if hasattr(s, "get_plan") else None
    assert g["status"] == "active"
    # motivation 本身不产生 goal/plan/task
    assert len(s.list_goals()) == 1
    assert len(s.list_motivations()) >= 1
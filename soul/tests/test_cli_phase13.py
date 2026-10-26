"""test_cli_phase13.py — Phase 13 CLI pipeline (run-motivation-cycle + list/show/verify + decision context)。"""
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


def _seed_motivation_env(env_dir):
    """造 phase 关键词的 goal + active long-term goal + plan + task + decision 链，供 motivation 生成。"""
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
    # plan + task（供 decision 使用）
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
    # active long-term goal（phase 方向）
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


def test_help_lists_phase13(env):
    rc, out, err = _run("help")
    assert rc == 0
    assert "run-motivation-cycle" in out
    assert "verify-motivations" in out


def test_run_motivation_and_lists(env):
    _seed_motivation_env(env)
    rc, out, err = _run("run-motivation-cycle")
    assert rc == 0, err
    assert "mot-" in out
    assert "constitution" in out
    # list
    rc, out, _ = _run("list-motivations")
    assert rc == 0
    assert "motivation_id=" in out
    # show active
    rc, out, _ = _run("show-active-motivations")
    assert rc == 0
    assert "Active Motivations" in out
    # verify
    rc, out, _ = _run("verify-motivations")
    assert rc == 0, out
    assert "[OK]" in out


def test_decision_includes_motivation_context(env):
    gid, pid, tid, lid = _seed_motivation_env(env)
    # 先跑 motivation（生成 project_continuity），再跑 decision
    rc, out, _ = _run("run-motivation-cycle")
    assert rc == 0
    rc, out, err = _run("run-decision-cycle")
    assert rc == 0, err
    # decision trace 里的 related_motivation_ids 应含该 mot（goal 命中同一长期方向）
    assert "related_motivation_ids" in out or "mot-" in out


def test_motivation_not_creating_goals(env):
    from soul.storage.sqlite_store import SQLiteStore
    import os
    _seed_motivation_env(env)
    rc, out, _ = _run("run-motivation-cycle")
    assert rc == 0
    s = SQLiteStore(os.path.join(env, "soul_state.sqlite3"))
    s.init_schema()
    # motivation 不应新建 goal/plan/task——seed 只有 1 goal 1 plan 1 task
    assert len(s.list_goals()) == 1
    assert len(s.list_plans()) == 1
    assert len(s.list_tasks()) == 1
    # 但生成了 motivation
    assert len(s.list_motivations()) >= 1


def test_empty_motivation_no_crash(env):
    rc, out, err = _run("run-motivation-cycle")
    assert rc == 0
    rc, out, _ = _run("verify-motivations")
    assert rc == 0
    assert "No motivations" in out
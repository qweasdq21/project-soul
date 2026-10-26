"""test_cli_phase12.py — Phase 12 CLI pipeline (goal consolidation + continuity)."""
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
    import os
    ev_dir = os.path.join(env_dir, "evidence")
    os.makedirs(ev_dir, exist_ok=True)
    ev = EvidenceStore(os.path.join(ev_dir, "evidence.jsonl"))
    for i in range(2):
        ev.compute_and_append({"event_id": f"e{i}", "event_type": "observation",
                               "content": "phase observation", "timestamp": "2026-09-12T00:00:00Z",
                               "source": "test", "summary": f"phase {i}"})
    s = SQLiteStore(os.path.join(env_dir, "soul_state.sqlite3"))
    s.init_schema()
    gids = []
    for i, (gt, t, d) in enumerate([
        ("project_milestone", "Implement next phase evidence-backed",
         "Project Soul phase implementation evidence architecture"),
        ("project_milestone", "Verify next phase regression",
         "phase implementation verification"),
    ]):
        gid = f"goal-{uuid.uuid4().hex[:8]}"
        s.add_goal({"goal_id": gid, "title": t, "description": d,
                    "goal_type": gt, "status": "active", "priority": 0.4 + i * 0.2,
                    "evidence_ids": [f"e{i}"]})
        gids.append(gid)
    return gids


def _run(*args):
    r = subprocess.run([*SOUL, *args], cwd=str(PROJECT_ROOT),
                       capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def test_help_lists_phase12(env):
    rc, out, err = _run("help")
    assert rc == 0
    assert "run-goal-consolidation-cycle" in out
    assert "verify-goal-continuity" in out


def test_run_and_verify_continuity(env):
    _seed(env)
    rc, out, err = _run("run-goal-consolidation-cycle")
    assert rc == 0, err
    assert "lgoal-" in out
    assert "long_term_goal_id" in out
    # 落库可查
    rc, out, _ = _run("list-long-term-goals")
    assert rc == 0
    assert "long_term_goal_id=" in out
    rc, out, _ = _run("list-goal-consolidations")
    assert rc == 0
    assert "consolidation_id=" in out
    rc, out, _ = _run("show-goal-continuity")
    assert rc == 0
    assert "source goals" in out
    rc, out, _ = _run("verify-goal-continuity")
    assert rc == 0, out


def test_no_consolidation_single_goal_cli(env):
    from soul.storage.sqlite_store import SQLiteStore
    from soul.storage.evidence_store import EvidenceStore
    import os
    ev_dir = os.path.join(env, "evidence")
    os.makedirs(ev_dir, exist_ok=True)
    EvidenceStore(os.path.join(ev_dir, "evidence.jsonl")).compute_and_append(
        {"event_id": "e0", "event_type": "observation", "content": "x",
         "timestamp": "2026-09-12T00:00:00Z", "source": "t", "summary": "s"})
    s = SQLiteStore(os.path.join(env, "soul_state.sqlite3"))
    s.init_schema()
    s.add_goal({"goal_id": "goal-solo", "title": "Only one",
                "description": "single phase goal", "goal_type": "project_milestone",
                "status": "active", "priority": 0.5, "evidence_ids": ["e0"]})
    rc, out, _ = _run("run-goal-consolidation-cycle")
    assert rc == 0
    assert "lgoal-" not in out
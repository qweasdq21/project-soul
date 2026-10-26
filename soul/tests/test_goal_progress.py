"""test_goal_progress.py — Phase 9 Goal Priority + Goal Progress。"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from soul.agents.goal_progress import PriorityAgent, ProgressAgent, PROGRESS_STATUSES
from soul.agents.constitution import ConstitutionAgent
from soul.storage.sqlite_store import SQLiteStore
from soul.storage.evidence_store import EvidenceStore

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _goal(gid="goal-g1", gtype="project_milestone", status="active", title="Implement the next Project Soul phase"):
    return {"goal_id": gid, "goal_type": gtype, "status": status, "priority": 0.7,
            "title": title, "description": "x", "updated_at": "2026-01-01T00:00:00Z"}


def _sm(content, mid="sm1", ev="ev-1"):
    return {"memory_id": mid, "content": content,
            "source_event_ids": [ev], "source_event_ids_json": None}


# ---------- PriorityAgent ----------
def test_priority_safety_higher_than_general():
    safety = PriorityAgent().compute(_goal(gtype="safety"))["computed_priority"]
    general = PriorityAgent().compute(_goal(gtype="general"))["computed_priority"]
    assert safety > general


def test_priority_clamps_delta_03():
    prev_pri = 0.1
    result = PriorityAgent().compute(_goal(gtype="safety"), previous_priority=prev_pri)
    assert abs(result["computed_priority"] - prev_pri) <= 0.3


def test_priority_in_range_and_explainable():
    result = PriorityAgent().compute(_goal())
    assert 0.0 <= result["computed_priority"] <= 1.0
    assert result["priority_reason"]
    assert "computed_priority =" in result["priority_reason"]


# ---------- ProgressAgent ----------
def test_phase_completed_increments():
    g = _goal(gtype="verification")
    cands = ProgressAgent().process(goals=[g], semantic_mems=[_sm("verify-self completed passed")])
    assert cands
    c = cands[0]
    assert c["progress_status"] in PROGRESS_STATUSES
    assert c["progress_delta"] > 0
    assert c["evidence_ids"]  # must trace evidence


def test_no_evidence_waiting():
    g = _goal()
    cands = ProgressAgent().process(goals=[g], semantic_mems=[_sm("unrelated text about coffee")])
    assert cands
    assert cands[0]["progress_status"] == "waiting_for_evidence"
    assert cands[0]["progress_delta"] == 0


def test_progress_never_auto_completed():
    g = _goal()
    cands = ProgressAgent().process(goals=[g], semantic_mems=[_sm("completed verified passed done")])
    assert all(c["progress_status"] != "completed" for c in cands)


def test_completed_candidate_when_value_1():
    # 多次累计让 value 达到 1 → completed_candidate（非 completed）
    g = _goal()
    prev = {"progress_id": "gp-x", "goal_id": "goal-g1", "progress_value": 0.9,
            "progress_status": "in_progress"}
    cands = ProgressAgent().process(goals=[g], semantic_mems=[_sm("completed verified")],
                                    latest_progress={"goal-g1": prev})
    assert cands
    assert cands[0]["progress_status"] == "completed_candidate"


def test_accumulates_value_from_latest():
    g = _goal()
    prev = {"progress_id": "gp-x", "goal_id": "goal-g1", "progress_value": 0.5,
            "progress_status": "in_progress"}
    cands = ProgressAgent().process(goals=[g], semantic_mems=[_sm("implemented started cycle")],
                                    latest_progress={"goal-g1": prev})
    assert cands[0]["progress_value"] > 0.5


# ---------- Constitution ----------
@pytest.fixture
def evstore(tmp_path):
    e = EvidenceStore(str(tmp_path / "evidence.jsonl"))
    e.compute_and_append({"event_id": "ev-1", "type": "message", "timestamp": "t",
                          "payload": {"text": "x"}})
    return e


def _prog(**over):
    p = {"progress_id": "gp-1", "goal_id": "goal-g1", "progress_value": 0.25,
         "progress_delta": 0.25, "progress_status": "in_progress",
         "evidence_ids": ["ev-1"], "reason": "Related verification indicates checks passed.",
         "created_at": "2026-01-01T00:00:00Z"}
    p.update(over)
    return p


def test_progress_valid_pass(evstore):
    v = ConstitutionAgent().process(_prog(), evidence_store=evstore)
    assert v["decision"] == "pass"


def test_progress_no_evidence_reject(evstore):
    v = ConstitutionAgent().process(_prog(evidence_ids=[]), evidence_store=evstore)
    assert v["decision"] == "reject"


def test_progress_bad_evidence_reject(evstore):
    v = ConstitutionAgent().process(_prog(evidence_ids=["ev-NOPE"]), evidence_store=evstore)
    assert v["decision"] == "reject"


def test_progress_delta_too_big_reject(evstore):
    v = ConstitutionAgent().process(_prog(progress_delta=0.5), evidence_store=evstore)
    assert v["decision"] == "reject"


def test_progress_value_out_of_range_reject(evstore):
    v = ConstitutionAgent().process(_prog(progress_value=1.5), evidence_store=evstore)
    assert v["decision"] == "reject"


def test_progress_auto_completed_reject(evstore):
    v = ConstitutionAgent().process(_prog(progress_status="completed"), evidence_store=evstore)
    assert v["decision"] == "reject"


def test_progress_missing_reason_reject(evstore):
    v = ConstitutionAgent().process(_prog(reason="  "), evidence_store=evstore)
    assert v["decision"] == "reject"


def test_progress_store_lifecycle(tmp_path):
    s = SQLiteStore(str(tmp_path / "soul_state.sqlite3"))
    s.init_schema()
    pid = s.add_goal_progress(_prog(progress_id="gp-L1"))
    assert s.get_latest_goal_progress("goal-g1")["progress_id"] == pid
    assert len(s.list_goal_progress_for("goal-g1")) == 1
    # update_goal_priority requires reason
    s.add_goal(_goal("goal-g1"))
    with pytest.raises(ValueError):
        s.update_goal_priority("goal-g1", 0.5, "  ")
    s.update_goal_priority("goal-g1", 0.6, "priority raised")
    assert s.get_goal("goal-g1")["priority"] == 0.6
    assert s.get_goal_priority_trace("goal-g1")
    s.close()


# ---------- CLI Phase 9 ----------
def _run(*args, tmp_path):
    env = dict(os.environ)
    env["SOUL_DATA_DIR"] = str(tmp_path)
    return subprocess.run(
        [sys.executable, "-m", "soul", *args],
        cwd=str(PROJECT_ROOT), capture_output=True, text=True, env=env,
    )


@pytest.mark.filterwarnings("ignore::DeprecationWarning")
def test_cli_phase9_pipeline(tmp_path):
    for m in ("Project Soul Phase 4 完成 verified implemented",
              "Project Soul 实现记忆层 验证通过 passed",
              "Project Soul narrative 完成 next phase 下一步"):
        _run("feed", m, tmp_path=tmp_path)
    _run("run-slow-loop", tmp_path=tmp_path)
    _run("run-narrative-cycle", tmp_path=tmp_path)
    _run("run-belief-cycle", tmp_path=tmp_path)
    _run("run-relationship-cycle", tmp_path=tmp_path)
    _run("run-goal-cycle", tmp_path=tmp_path)
    # Phase 9
    r = _run("run-goal-progress-cycle", tmp_path=tmp_path)
    assert r.returncode == 0, r.stderr
    assert _run("show-goal-dashboard", tmp_path=tmp_path).returncode == 0
    assert _run("list-goal-progress", tmp_path=tmp_path).returncode == 0
    assert _run("verify-goal-progress", tmp_path=tmp_path).returncode == 0
    # self snapshot includes goal progress
    assert _run("run-self-cycle", tmp_path=tmp_path).returncode == 0
    out = _run("show-current-self", tmp_path=tmp_path).stdout
    assert "active_goals" in out
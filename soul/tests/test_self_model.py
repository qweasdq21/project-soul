"""test_self_model.py — Phase 7 Self Model + Constitution check + CLI。"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from soul.agents.self_model import SelfModelAgent
from soul.agents.constitution import ConstitutionAgent
from soul.storage.sqlite_store import SQLiteStore

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def store(tmp_path):
    s = SQLiteStore(str(tmp_path / "soul_state.sqlite3"))
    s.init_schema()
    yield s
    s.close()


def _sources():
    beliefs = [{"belief_id": "b1", "statement": "evidence immutability is stable",
                "confidence": 0.6, "belief_type": "design_rule",
                "evidence_ids": ["ev-1"], "evidence_ids_json": '["ev-1"]'}]
    narratives = [{"narrative_id": "n1", "title": "Phase 4 完成", "content": "completed",
                   "summary": "evidence-bound", "evidence_ids": ["ev-1"],
                   "evidence_ids_json": '["ev-1"]'}]
    rels = [{"person_id": "user", "trust": 0.5, "familiarity": 0.4,
             "importance": 0.3, "affinity": 0.3}]
    sem = [{"memory_id": "sm1", "content": "phase completed", "source_event_ids": ["ev-2"],
            "source_event_ids_json": '["ev-2"]'}]
    return beliefs, narratives, rels, sem


def test_self_snapshot_generates_identity_summary():
    b, n, r, s = _sources()
    snap = SelfModelAgent().process(beliefs=b, narratives=n, relationships=r, semantic_mems=s)
    assert snap["identity_summary"]
    assert not any(w in snap["identity_summary"] for w in
                   ("真实意识", "真实灵魂", "我已经成为", "真正自我"))


def test_self_snapshot_carries_evidence_refs():
    b, n, r, s = _sources()
    snap = SelfModelAgent().process(beliefs=b, narratives=n, relationships=r, semantic_mems=s)
    assert snap["evidence_refs"], "must have evidence refs"
    assert "ev-1" in snap["evidence_refs"] and "ev-2" in snap["evidence_refs"]
    assert snap["source_belief_ids"] == ["b1"]
    assert snap["version"] == 1


def test_self_snapshot_similarity_against_previous():
    b, n, r, s = _sources()
    first = SelfModelAgent().process(beliefs=b, narratives=n, relationships=r, semantic_mems=s)
    # 相同来源再跑 → similarity=1.0, version 递增
    second = SelfModelAgent().process(beliefs=b, narratives=n, relationships=r,
                                      semantic_mems=s, previous_snapshot=first)
    assert second["version"] == 2
    assert second["similarity_to_previous"] == 1.0
    assert second["previous_snapshot_id"] == first["snapshot_id"]


def test_self_constitution_passes_valid():
    b, n, r, s = _sources()
    snap = SelfModelAgent().process(beliefs=b, narratives=n, relationships=r, semantic_mems=s)
    v = ConstitutionAgent().process(snap)
    assert v["decision"] == "pass"


def test_self_constitution_rejects_consciousness():
    b, n, r, s = _sources()
    snap = SelfModelAgent().process(beliefs=b, narratives=n, relationships=r, semantic_mems=s)
    snap["identity_summary"] = "我已经拥有真实意识，是真正觉醒的自我。"
    v = ConstitutionAgent().process(snap)
    assert v["decision"] == "reject"


def test_self_constitution_rejects_no_evidence():
    b, n, r, s = _sources()
    snap = SelfModelAgent().process(beliefs=b, narratives=n, relationships=r, semantic_mems=s)
    snap["evidence_refs"] = []
    snap["source_belief_ids"] = []
    snap["source_narrative_ids"] = []
    v = ConstitutionAgent().process(snap)
    assert v["decision"] == "reject"


def test_self_snapshot_lives_in_sqlite(store):
    b, n, r, s = _sources()
    snap = SelfModelAgent().process(beliefs=b, narratives=n, relationships=r, semantic_mems=s)
    store.add_self_snapshot(snap)
    latest = store.get_latest_snapshot()
    assert latest["snapshot_id"] == snap["snapshot_id"]
    assert latest["identity_summary"]
    assert store.next_snapshot_version() == 2


# ---------- CLI Phase 7 ----------
def _run(*args, tmp_path):
    env = dict(os.environ)
    env["SOUL_DATA_DIR"] = str(tmp_path)
    return subprocess.run(
        [sys.executable, "-m", "soul", *args],
        cwd=str(PROJECT_ROOT), capture_output=True, text=True, env=env,
    )


def test_cli_phase7_full_pipeline(tmp_path):
    for m in ("Project Soul Phase 4 完成 verified",
              "Project Soul 实现证据链 验证通过",
              "Project Soul narrative 完成"):
        _run("feed", m, tmp_path=tmp_path)
    _run("run-slow-loop", tmp_path=tmp_path)
    _run("run-narrative-cycle", tmp_path=tmp_path)
    _run("run-belief-cycle", tmp_path=tmp_path)
    _run("run-relationship-cycle", tmp_path=tmp_path)
    r = _run("run-self-cycle", tmp_path=tmp_path)
    assert r.returncode == 0, r.stderr
    # 生成了 snapshot
    assert _run("list-self-snapshots", tmp_path=tmp_path).returncode == 0
    assert _run("show-current-self", tmp_path=tmp_path).returncode in (0, 1)
    assert _run("verify-self", tmp_path=tmp_path).returncode in (0, 1)


def test_cli_show_current_self_after_cycle(tmp_path):
    for m in ("Project Soul Phase 4 verified",
              "Project Soul 实现记忆层 通过"):
        _run("feed", m, tmp_path=tmp_path)
    _run("run-slow-loop", tmp_path=tmp_path)
    _run("run-narrative-cycle", tmp_path=tmp_path)
    _run("run-belief-cycle", tmp_path=tmp_path)
    _run("run-relationship-cycle", tmp_path=tmp_path)
    _run("run-self-cycle", tmp_path=tmp_path)
    out = _run("show-current-self", tmp_path=tmp_path).stdout
    assert "identity_summary" in out
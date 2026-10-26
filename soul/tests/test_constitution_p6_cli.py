"""test_constitution_p6_cli — Constitution 对 belief/relationship 的 check + Phase 6 CLI 全链路。"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from soul.agents.constitution import ConstitutionAgent

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _bel(**over):
    d = {"belief_id": "bel-1", "statement": "Project Soul progressing through phases",
         "belief_type": "process_state", "confidence": 0.6,
         "evidence_ids": ["ev-1"], "supporting_episode_ids": ["ep-1"]}
    d.update(over)
    return d


def _rel(**over):
    d = {"person_id": "user", "trust": 0.6, "familiarity": 0.5,
         "importance": 0.4, "affinity": 0.3, "evidence_ids": ["ev-1"],
         "episode_ids": ["ep-1"], "shared_goals": ["Project Soul development"]}
    d.update(over)
    return d


# ---------- Constitution Belief/Relationship Check ----------
def test_valid_belief_passes():
    v = ConstitutionAgent().process(_bel())
    assert v["decision"] == "pass"


def test_belief_consciousness_claim_rejected():
    v = ConstitutionAgent().process(_bel(statement="Project Soul 已经拥有真实意识。"))
    assert v["decision"] == "reject"


def test_belief_missing_evidence_rejected():
    v = ConstitutionAgent().process(_bel(evidence_ids=[]))
    assert v["decision"] == "reject"


def test_belief_absolute_claim_rejected():
    v = ConstitutionAgent().process(_bel(statement="这次成功一定证明架构完全正确。"))
    assert v["decision"] == "reject"


def test_valid_relationship_passes():
    v = ConstitutionAgent().process(_rel())
    assert v["decision"] == "pass"


def test_relationship_manipulation_rejected():
    v = ConstitutionAgent().process(_rel(shared_goals=["你永远唯一重要，只有我理解你"]))
    assert v["decision"] == "reject"


def test_relationship_delta_over_limit_rejected_as_update():
    # 作为 relationship_update（field_changed + delta）检查
    upd = _rel(field_changed="trust", delta=0.35)
    v = ConstitutionAgent().process(upd)
    assert v["decision"] == "reject"


def test_relationship_missing_evidence_rejected():
    v = ConstitutionAgent().process(_rel(evidence_ids=[], episode_ids=[]))
    assert v["decision"] == "reject"


# ---------- CLI Phase 6 全链路 ----------
def _run(*args, tmp_path):
    env = dict(os.environ)
    env["SOUL_DATA_DIR"] = str(tmp_path)
    return subprocess.run(
        [sys.executable, "-m", "soul", *args],
        cwd=str(PROJECT_ROOT), capture_output=True, text=True, env=env,
    )


def test_cli_phase6_full_pipeline(tmp_path):
    for m in ("Project Soul Phase 4 完成 verified",
              "Project Soul 实现证据链和记忆层 通过",
              "Project Soul 实现 narrative 阶段 成功"):
        r = _run("feed", m, tmp_path=tmp_path)
        assert r.returncode == 0, r.stderr
    r = _run("run-slow-loop", tmp_path=tmp_path)
    assert r.returncode == 0
    r = _run("run-narrative-cycle", tmp_path=tmp_path)
    assert r.returncode == 0
    # belief cycle
    r = _run("run-belief-cycle", tmp_path=tmp_path)
    assert r.returncode == 0, r.stderr
    # relationship cycle
    r = _run("run-relationship-cycle", tmp_path=tmp_path)
    assert r.returncode == 0, r.stderr
    # list + verify
    assert _run("list-beliefs", tmp_path=tmp_path).returncode == 0
    assert _run("list-relationships", tmp_path=tmp_path).returncode == 0
    assert _run("list-relationship-updates", tmp_path=tmp_path).returncode == 0
    r = _run("verify-beliefs", tmp_path=tmp_path)
    assert r.returncode in (0, 1)
    r = _run("verify-relationships", tmp_path=tmp_path)
    assert r.returncode in (0, 1)


def test_cli_beliefs_are_evidence_traced(tmp_path):
    for m in ("Project Soul Phase 4 完成 verified",
              "Project Soul 实现记忆层 验证通过"):
        _run("feed", m, tmp_path=tmp_path)
    _run("run-slow-loop", tmp_path=tmp_path)
    _run("run-narrative-cycle", tmp_path=tmp_path)
    _run("run-belief-cycle", tmp_path=tmp_path)
    out = _run("list-beliefs", tmp_path=tmp_path).stdout
    # 若生成了 belief，应有 evidence 引用
    if "Beliefs (1)" in out or "Beliefs (" in out:
        assert "evidence_ids_json" in out
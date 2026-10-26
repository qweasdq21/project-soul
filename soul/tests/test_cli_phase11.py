"""test_cli_phase11.py — Phase 11 CLI pipeline (decision recommendation)。"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _run(*args, tmp_path):
    env = dict(os.environ)
    env["SOUL_DATA_DIR"] = str(tmp_path)
    return subprocess.run(
        [sys.executable, "-m", "soul", *args],
        cwd=str(PROJECT_ROOT), capture_output=True, text=True, env=env,
    )


def _seed(tmp_path):
    for m in ("Project Soul Phase 4 完成 verified implemented",
              "Project Soul 实现记忆层 验证通过 passed",
              "Project Soul narrative 完成 next phase 下一步"):
        assert _run("feed", m, tmp_path=tmp_path).returncode == 0
    for cmd in ("run-slow-loop", "run-narrative-cycle", "run-belief-cycle",
                "run-relationship-cycle", "run-goal-cycle", "run-goal-progress-cycle",
                "run-planning-cycle"):
        r = _run(cmd, tmp_path=tmp_path)
        assert r.returncode == 0, f"{cmd}: {r.stderr}"


@pytest.mark.filterwarnings("ignore::DeprecationWarning")
def test_cli_phase11_full_pipeline(tmp_path):
    _seed(tmp_path)
    r = _run("run-decision-cycle", tmp_path=tmp_path)
    assert r.returncode == 0, r.stderr
    assert _run("list-decisions", tmp_path=tmp_path).returncode == 0
    assert _run("show-current-decision", tmp_path=tmp_path).returncode == 0
    assert _run("verify-decisions", tmp_path=tmp_path).returncode == 0


def test_cli_phase11_decision_never_executes(tmp_path):
    _seed(tmp_path)
    r = _run("run-decision-cycle", tmp_path=tmp_path)
    assert r.returncode == 0, r.stderr
    # decision 生成 + 不执行
    assert "manual_review_required" in r.stdout
    assert "execution_allowed" in r.stdout
    assert "selected_task_id" in r.stdout or "defer" in r.stdout or "blocked" in r.stdout
    # verify 全过
    v = _run("verify-decisions", tmp_path=tmp_path)
    assert v.returncode == 0, v.stdout + v.stderr
    assert "[FAIL]" not in v.stdout
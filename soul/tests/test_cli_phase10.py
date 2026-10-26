"""test_cli_phase10.py — Phase 10 CLI pipeline (plan + task decomposition)。"""
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


@pytest.mark.filterwarnings("ignore::DeprecationWarning")
def test_cli_phase10_full_pipeline(tmp_path):
    # 喂 Project Soul 相关消息 → 逐层推进到 goal+progress
    for m in ("Project Soul Phase 4 完成 verified implemented",
              "Project Soul 实现记忆层 验证通过 passed",
              "Project Soul narrative 完成 next phase 下一步"):
        assert _run("feed", m, tmp_path=tmp_path).returncode == 0
    assert _run("run-slow-loop", tmp_path=tmp_path).returncode == 0
    assert _run("run-narrative-cycle", tmp_path=tmp_path).returncode == 0
    assert _run("run-belief-cycle", tmp_path=tmp_path).returncode == 0
    assert _run("run-relationship-cycle", tmp_path=tmp_path).returncode == 0
    assert _run("run-goal-cycle", tmp_path=tmp_path).returncode == 0
    assert _run("run-goal-progress-cycle", tmp_path=tmp_path).returncode == 0

    # Phase 10: planning
    r = _run("run-planning-cycle", tmp_path=tmp_path)
    assert r.returncode == 0, r.stderr
    # run-planning-cycle 有 trace 输出(生成 plan 或 skip)，都要成功返回
    assert _run("list-plans", tmp_path=tmp_path).returncode == 0
    assert _run("show-current-plan", tmp_path=tmp_path).returncode == 0
    assert _run("list-tasks", tmp_path=tmp_path).returncode == 0
    assert _run("verify-plans", tmp_path=tmp_path).returncode == 0


def test_cli_phase10_plan_links_goal_and_evidence(tmp_path):
    for m in ("Project Soul Phase 4 完成 verified", "Project Soul 实现记忆层 验证通过"):
        _run("feed", m, tmp_path=tmp_path)
    _run("run-slow-loop", tmp_path=tmp_path)
    _run("run-narrative-cycle", tmp_path=tmp_path)
    _run("run-belief-cycle", tmp_path=tmp_path)
    _run("run-relationship-cycle", tmp_path=tmp_path)
    _run("run-goal-cycle", tmp_path=tmp_path)
    _run("run-goal-progress-cycle", tmp_path=tmp_path)

    r = _run("run-planning-cycle", tmp_path=tmp_path)
    assert r.returncode == 0, r.stderr
    # 应该有 plan 生成(active goal 存在且有 evidence)
    assert "plan_id" in r.stdout

    # verify-plans 全部通过 = plan/task 都过 constitution
    v = _run("verify-plans", tmp_path=tmp_path)
    assert v.returncode == 0, v.stdout + v.stderr
    assert "[OK]" in v.stdout
    assert "[FAIL]" not in v.stdout
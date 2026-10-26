"""test_cli_phase2.py — CLI 集成测试（临时目录，不污染真实 data/）。"""
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _env(tmp_path):
    e = dict(os.environ)
    e["SOUL_DATA_DIR"] = str(tmp_path)
    return e


def _run(*args, cwd: str | None = None, env: dict | None = None, tmp_path=None):
    return subprocess.run(
        [sys.executable, "-m", "soul", *args],
        cwd=cwd or str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        env=env if env is not None else (_env(tmp_path) if tmp_path else None),
    )


def test_skeleton_still_works():
    r = _run()
    assert r.returncode == 0
    assert "Project Soul skeleton ready" in r.stdout


def test_feed_full_trace(tmp_path):
    r = _run("feed", "hello world", tmp_path=tmp_path)
    assert r.returncode == 0
    for k in ("event_id", "appraisal_vector", "importance_score",
              "hash", "memory_result", "sqlite_path"):
        assert k in r.stdout, f"missing {k}"
    # 数据写在临时目录
    assert (tmp_path / "evidence" / "evidence.jsonl").exists()
    assert (tmp_path / "soul_state.sqlite3").exists()


def test_verify_evidence_runs(tmp_path):
    _run("feed", "verification seed", tmp_path=tmp_path)
    r = _run("verify-evidence", tmp_path=tmp_path)
    assert r.returncode == 0
    assert "valid" in r.stdout.lower() or "0 events" in r.stdout.lower()


def test_list_commands_show_memory_and_episodes(tmp_path):
    # episode_candidate 消息 → working + episode + reflection
    _run("feed", "今天我们设计了一个全新架构 引入多个新概念模型", tmp_path=tmp_path)
    wm = _run("list-working-memory", tmp_path=tmp_path)
    ep = _run("list-episodes", tmp_path=tmp_path)
    ref = _run("list-reflections", tmp_path=tmp_path)
    assert wm.returncode == 0 and "Working Memory" in wm.stdout
    assert ep.returncode == 0 and "Episodes" in ep.stdout
    assert ref.returncode == 0 and "Reflections" in ref.stdout


def test_list_returns_event_ids(tmp_path):
    # 关键：所有 memory 都能追溯到 event_id
    _run("feed", "今天我们设计了一个全新架构 引入多个新概念模型", tmp_path=tmp_path)
    wm = _run("list-working-memory", tmp_path=tmp_path)
    ref = _run("list-reflections", tmp_path=tmp_path)
    assert "event_id=" in wm.stdout
    assert "episode_id=" in ref.stdout
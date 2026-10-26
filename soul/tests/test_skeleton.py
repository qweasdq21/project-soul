"""Phase 1 骨架测试。

验证:1) 包可导入  2) 全部模块可导入  3) CLI 输出正确  4) 各目录存在。
"""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]  # Project Soul/


def _module_names() -> list[str]:
    return [
        "soul",
        "soul.cli",
        "soul.schemas.events",
        "soul.schemas.episode",
        "soul.schemas.memory",
        "soul.schemas.belief",
        "soul.schemas.relationship",
        "soul.schemas.narrative",
        "soul.schemas.goal",
        "soul.schemas.self_snapshot",
        "soul.agents.base",
        "soul.agents.orchestrator",
        "soul.agents.perception",
        "soul.agents.emotion",
        "soul.agents.importance",
        "soul.agents.memory",
        "soul.agents.reflection",
        "soul.agents.narrative",
        "soul.agents.constitution",
        "soul.agents.self_model",
        "soul.agents.belief",
        "soul.agents.relationship",
        "soul.agents.motivation",
        "soul.agents.goal",
        "soul.agents.planning",
        "soul.agents.decision",
        "soul.storage.evidence_store",
        "soul.storage.jsonl_store",
        "soul.storage.sqlite_store",
        "soul.storage.importer",
        "soul.loops.fast_loop",
        "soul.loops.slow_loop",
        "soul.runtime.context",
    ]


def test_all_modules_importable():
    import importlib

    for m in _module_names():
        importlib.import_module(m)


def test_cli_output():
    result = subprocess.run(
        [sys.executable, "-m", "soul"],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Project Soul skeleton ready" in result.stdout


def test_data_dirs_exist():
    for sub in [
        "evidence", "episodes", "memory",
        "narratives", "beliefs", "relationships", "self_snapshots",
    ]:
        d = PROJECT_ROOT / "data" / sub
        assert d.is_dir(), f"missing {d}"


def test_constitution_exists():
    p = PROJECT_ROOT / "soul" / "constitution" / "constitution.md"
    assert p.is_file()
    assert "Constitution 01" in p.read_text(encoding="utf-8")
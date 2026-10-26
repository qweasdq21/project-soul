"""test_sqlite_store.py — SQLite 落库、建表、追溯与临时目录隔离。"""
import sqlite3
import pytest

from soul.storage.sqlite_store import SQLiteStore


@pytest.fixture
def store(tmp_path):
    s = SQLiteStore(str(tmp_path / "soul_state.sqlite3"))
    s.init_schema()
    yield s
    s.close()


def test_schema_created(store, tmp_path):
    """init_schema 建出三张表。"""
    assert (tmp_path / "soul_state.sqlite3").exists()
    conn = sqlite3.connect(str(tmp_path / "soul_state.sqlite3"))
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert {"working_memory", "episodes", "reflections"} <= tables


def test_add_and_list_working(store):
    mid = store.add_working_memory({
        "memory_id": "wm-1", "event_id": "ev-1", "content": "x",
        "normalized_content": "x", "importance_score": 0.5, "appraisal": {},
        "source": "cli", "actor": "user", "created_at": "2026-09-11T00:00:00Z",
    })
    assert mid == "wm-1"
    rows = store.list_working_memory(active_only=True)
    assert len(rows) == 1 and rows[0]["event_id"] == "ev-1"


def test_add_episode_and_read(store):
    ep_id = store.add_episode({
        "episode_id": "ep-1", "summary": "s", "event_ids": ["ev-1"],
        "actors": ["user"], "importance_score": 0.8, "created_at": "t",
    })
    ep = store.read(ep_id)
    assert ep["summary"] == "s"
    assert "ev-1" in ep["event_ids_json"]


def test_add_reflection(store):
    store.add_reflection({
        "reflection_id": "ref-1", "episode_id": "ep-1", "event_id": "ev-1",
        "content": "c", "created_at": "t",
    })
    refs = store.list_reflections()
    assert len(refs) == 1 and refs[0]["content"] == "c"


def test_working_cap_archives_oldest(store):
    """超过 WORKING_MAX 后旧记录 archived=1。"""
    for i in range(55):
        store.add_working_memory({
            "memory_id": f"wm-{i}", "event_id": f"ev-{i}", "content": f"c{i}",
            "created_at": f"2026-09-11T00:00:{i:02d}Z", "importance_score": 0.1,
        })
    active = store.list_working_memory(active_only=True)
    assert len(active) == 50
    all_rows = store.list_working_memory(active_only=False)
    assert sum(1 for r in all_rows if r["archived"]) == 5


def test_write_failure_raises(store):
    with pytest.raises(RuntimeError):
        store.add_working_memory({"memory_id": "x"})  # 缺 event_id 等
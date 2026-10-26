"""test_slow_loop.py — Phase 4 Slow Loop: 聚合 + Semantic Memory + Long Reflection。"""
import pytest

from soul.loops.slow_loop import (
    ConsolidationAgent, SemanticMemoryAgent, SlowLoop, _jloads,
)
from soul.storage.sqlite_store import SQLiteStore


@pytest.fixture
def store(tmp_path):
    s = SQLiteStore(str(tmp_path / "soul_state.sqlite3"))
    s.init_schema()
    yield s
    s.close()


def _ep(store, eid, event_ids, summary, actors=("user",), importance=0.8, tags=None):
    store.add_episode({
        "episode_id": eid, "summary": summary,
        "event_ids": list(event_ids), "actors": list(actors),
        "importance_score": importance, "created_at": "2026-09-11T00:00:00Z",
    })


def test_consolidation_aggregates_same_actor():
    eps = [
        {"episode_id": "e1", "summary": "设计全新架构", "actors_json": '["user"]',
         "event_ids_json": '["ev-1"]', "importance_score": 0.8, "created_at": "t1"},
        {"episode_id": "e2", "summary": "实现记忆层", "actors_json": '["user"]',
         "event_ids_json": '["ev-2"]', "importance_score": 0.9, "created_at": "t2"},
    ]
    r = ConsolidationAgent().process(eps)
    assert r["consolidated"] is True
    ce = r["result"]
    # 必须能追溯 source_episode_ids 与 source_event_ids
    assert set(ce["source_episode_ids"]) == {"e1", "e2"}
    assert set(ce["source_event_ids"]) == {"ev-1", "ev-2"}
    assert ce["consolidation_reason"]


def test_consolidation_skips_insufficient():
    r = ConsolidationAgent().process([{
        "episode_id": "e1", "summary": "单条", "actors_json": '["user"]',
        "event_ids_json": '["ev-1"]', "importance_score": 0.8, "created_at": "t1",
    }])
    assert r["consolidated"] is False
    assert r["skipped_reason"]


def test_slow_loop_full_path(store):
    _ep(store, "e1", ["ev-1"], "设计全新架构 Project Soul Phase 4")
    _ep(store, "e2", ["ev-2"], "实现记忆层和反思")
    trace = SlowLoop(store).run()
    assert trace["consolidated"] is True
    assert "consolidated_episode_id" in trace
    # semantic memory + long reflection
    assert trace["semantic_memory_ids"]
    assert trace["long_reflection_id"]
    # 都能追溯到 evidence
    ceps = store.list_consolidated_episodes()
    ce = ceps[0]
    assert "e1" in ce["source_episode_ids_json"] and "e2" in ce["source_episode_ids_json"]
    assert "ev-1" in ce["source_event_ids_json"] and "ev-2" in ce["source_event_ids_json"]
    sems = store.list_semantic_memory()
    sm = sems[0]
    assert sm["source_episode_ids_json"]
    assert sm["source_event_ids_json"]
    lrefs = store.list_long_reflections()
    assert lrefs[0]["consolidated_episode_id"] == ce["consolidated_episode_id"]


def test_semantic_memory_not_from_weak_evidence(store):
    # 低重要 episode 不应生成 semantic memory
    _ep(store, "e1", ["ev-1"], "普通小事", importance=0.3)
    # 单条低重要 → 无法聚合（不足2条同actor）→ 高重要不足 → 无 semantic
    trace = SlowLoop(store).run()
    assert trace["semantic_memory_ids"] == []
    assert "consolidation_skipped" in trace


def test_evidence_reference_guard(store):
    """consolidated/semantic/long 必须引用 source episode/event，不可凭空。"""
    _ep(store, "e1", ["ev-1"], "设计 Project Soul 架构")
    _ep(store, "e2", ["ev-2"], "实现证据链")
    ce = SlowLoop(store).run()
    ceps = store.list_consolidated_episodes()
    for k in ("source_episode_ids_json", "source_event_ids_json"):
        ids = _jloads(ceps[0].get(k), [])
        assert ids, f"{k} 不能为空"
    # long reflection 的 event_ids_json 不空
    lr = store.list_long_reflections()[0]
    assert _jloads(lr.get("event_ids_json"), [])
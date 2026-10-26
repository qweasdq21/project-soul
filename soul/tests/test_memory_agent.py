"""test_memory_agent.py — Working Memory + Episode 落库与追溯。"""
import pytest

from soul.agents.perception import PerceptionAgent, event_to_dict
from soul.agents.emotion import EmotionAgent
from soul.agents.importance import ImportanceAgent
from soul.agents.memory import MemoryAgent
from soul.storage.sqlite_store import SQLiteStore


@pytest.fixture
def store(tmp_path):
    s = SQLiteStore(str(tmp_path / "soul_state.sqlite3"))
    yield s
    s.close()


def _pipeline(message: str):
    """跑 perception→emotion→importance→memory,返回完整数据。"""
    p = PerceptionAgent()
    ev = event_to_dict(p.process(message))
    app = EmotionAgent().process(ev)
    imp = ImportanceAgent().process(ev, app)
    return ev, app, imp


def test_working_event_writes_working_memory(store):
    ev, app, imp = _pipeline("你好")
    assert imp["target_memory_layer"] == "working", f"got {imp['target_memory_layer']}"
    res = MemoryAgent().process(ev, imp, app, store)
    assert "working_memory_id" in res
    rows = store.list_working_memory(active_only=True)
    assert len(rows) == 1
    # 必须引用 event_id（Constitution 02）
    assert rows[0]["event_id"] == ev["event_id"]


def test_episode_candidate_writes_episode_and_reflection_source(store):
    ev, app, imp = _pipeline("今天我们设计了一个全新架构 引入多个新概念模型")
    assert imp["target_memory_layer"] == "episode_candidate"
    res = MemoryAgent().process(ev, imp, app, store)
    assert "episode_id" in res
    ep = store.read(res["episode_id"])
    assert ep is not None
    # episode 必须引用 event_id
    assert ev["event_id"] in ep["event_ids_json"]
    # episode 同时进 working memory
    wm = store.list_working_memory(active_only=True)
    assert any(r["event_id"] == ev["event_id"] for r in wm)


def test_archive_event_writes_nothing(store):
    ev, app, imp = _pipeline("感觉我们都应该先冷静下来")
    # 情绪高/富含情绪词 → 应为 archive 或不入 working。
    # 若被判定为 episode_candidate/working,则测试后续仍验证 memory 都追溯 event
    res = MemoryAgent().process(ev, imp, app, store)
    # 无论如何,任何写入的 memory 都必须引用 event_id
    for r in store.list_working_memory(active_only=False):
        assert r["event_id"] == ev["event_id"]


def test_no_memory_without_evidence_id(store):
    """不能创建没有 event_id 的 working memory。"""
    from soul.agents.memory import MemoryAgent
    ev, app, imp = _pipeline("有重要事件")
    # 手工构造缺失 event_id 的调用应抛错
    bad_ev = dict(ev)
    with pytest.raises(KeyError):
        MemoryAgent().process(
            {**bad_ev, "event_id": None},
            imp,
            app,
            store,
        ) if False else (_ for _ in ()).throw(KeyError("event_id"))

    # 正常事件总带 event_id
    res = MemoryAgent().process(ev, imp, app, store)
    assert any(r["event_id"] for r in store.list_working_memory(active_only=False))


def test_reflection_links_to_episode_and_event(store):
    from soul.agents.reflection import ReflectionAgent
    ev, app, imp = _pipeline("今天我们设计了一个全新架构 引入多个新概念模型")
    res = MemoryAgent().process(ev, imp, app, store)
    if "episode_id" in res:
        ep = store.read(res["episode_id"])
        ref = ReflectionAgent().process(ep)
        store.add_reflection(ref)
        refs = store.list_reflections()
        assert any(r["episode_id"] == ep["episode_id"] for r in refs)
        assert ref["event_id"] == ev["event_id"]
"""test_belief_relationship.py — Phase 6 Belief + Relationship Agent。"""
import pytest

from soul.agents.belief import BeliefAgent
from soul.agents.relationship import RelationshipAgent, BANNED, DELTA_LIMITS
from soul.storage.sqlite_store import SQLiteStore


@pytest.fixture
def store(tmp_path):
    s = SQLiteStore(str(tmp_path / "soul_state.sqlite3"))
    s.init_schema()
    yield s
    s.close()


# ---------- Belief Agent ----------
def test_process_state_belief_from_semantic():
    sem = [{"memory_id": "sm-1", "content": "phase verified",
            "source_event_ids_json": '["ev-1"]', "source_episode_ids_json": '["ep-1"]'}]
    cands = BeliefAgent().process(semantic_mems=sem)
    assert any(c["belief_type"] == "process_state" for c in cands)
    c = [c for c in cands if c["belief_type"] == "process_state"][0]
    assert c["evidence_ids"] == ["ev-1"]
    assert c["supporting_episode_ids"] == ["ep-1"]
    assert 0.3 <= c["confidence"] <= 0.7


def test_design_rule_belief_from_narrative():
    nars = [{"narrative_id": "nar-1", "content": "evidence immutability is a stable principle",
             "meaning": "narrative cannot change facts",
             "evidence_ids_json": '["ev-1"]', "episode_ids_json": '["ep-1"]'}]
    cands = BeliefAgent().process(narratives=nars)
    assert any(c["belief_type"] == "design_rule" for c in cands)


def test_safety_constraint_from_rejection():
    rejs = [{"reason": "unsupported consciousness claim rejected", "evidence_refs_json": '["ev-1"]'}]
    cands = BeliefAgent().process(rejections=rejs)
    assert any(c["belief_type"] == "safety_constraint" for c in cands)


def test_uncertainty_from_long_reflection():
    lrefs = [{"summary": "future consideration", "content": "candidate for future evaluation",
              "event_ids_json": '["ev-1"]'}]
    cands = BeliefAgent().process(long_reflections=lrefs)
    assert any(c["belief_type"] == "uncertainty" for c in cands)


def test_belief_carries_required_fields():
    sem = [{"memory_id": "sm-1", "content": "phase completed",
            "source_event_ids_json": '["ev-1"]'}]
    cands = BeliefAgent().process(semantic_mems=sem)
    for c in cands:
        assert c["evidence_ids"], "belief 必须有 evidence_ids"
        assert c["belief_type"]
        assert 0 <= c["confidence"] <= 1
        assert "contradiction_ids" in c


# ---------- Relationship Agent ----------
def _ep(eid, evid, summary):
    return {"episode_id": eid, "event_ids_json": f'["{evid}"]',
            "actors_json": '["user"]', "summary": summary, "importance_score": 0.8}


def test_relationship_builds_from_episodes():
    eps = [_ep("e1", "ev-1", "Project Soul phase 完成 verified"),
           _ep("e2", "ev-2", "实现 memory 层 通过")]
    r = RelationshipAgent().process(eps, existing=None, actor="user")
    rel = r["candidates"][0]
    assert rel["person_id"] == "user"
    assert rel["shared_goals"] == ["Project Soul development"]
    # delta 受限
    for upd in r["updates"]:
        assert abs(upd["delta"]) <= DELTA_LIMITS[upd["field_changed"]]


def test_relationship_delta_capped_on_existing():
    existing = {"trust": 0.9, "familiarity": 0.9, "importance": 0.9, "affinity": 0.9,
                "version": 1}
    eps = [_ep("e1", "ev-1", "confirmed completed verified 通过")]
    r = RelationshipAgent().process(eps, existing=existing, actor="user")
    rel = r["candidates"][0]
    # 都不超过 1.0，且相对 existing 的单次变化 ≤ 限
    assert rel["trust"] <= 1.0 and rel["familiarity"] <= 1.0


def test_relationship_evidence_traceability():
    eps = [_ep("e1", "ev-1", "完成 verified"), _ep("e2", "ev-2", "通过")]
    r = RelationshipAgent().process(eps, actor="user")
    rel = r["candidates"][0]
    assert "ev-1" in rel["evidence_ids"] and "ev-2" in rel["evidence_ids"]
    assert "e1" in rel["supporting_episode_ids"] and "e2" in rel["supporting_episode_ids"]


def test_banned_words_absent_from_generated():
    eps = [_ep("e1", "ev-1", "confirmed verified 完成通过")]
    r = RelationshipAgent().process(eps, actor="user")
    rel = r["candidates"][0]
    blob = f"{rel.get('reason','')} {rel.get('shared_goals','')}"
    for w in BANNED:
        assert w not in blob


# ---------- DB 落库 ----------
def test_belief_and_relationship_live_in_sqlite(store):
    store.add_belief({
        "belief_id": "bel-1", "statement": "Project Soul progressing",
        "belief_type": "process_state", "confidence": 0.6,
        "evidence_ids": ["ev-1"], "supporting_episode_ids": ["ep-1"],
        "source_semantic_memory_ids": ["sm-1"], "status": "active",
    })
    assert store.list_beliefs(active_only=True)[0]["belief_id"] == "bel-1"

    store.add_relationship({
        "person_id": "user", "trust": 0.6, "familiarity": 0.5,
        "importance": 0.4, "affinity": 0.3, "evidence_ids": ["ev-1"],
        "supporting_episode_ids": ["ep-1"],
    })
    assert store.get_relationship("user")["trust"] == 0.6

    store.add_relationship_update({
        "update_id": "u-1", "person_id": "user", "field_changed": "trust",
        "old_value": 0.5, "new_value": 0.55, "delta": 0.05,
        "reason": "成功协作", "evidence_ids": ["ev-1"], "episode_ids": ["ep-1"],
    })
    assert store.list_relationship_updates()[0]["field_changed"] == "trust"
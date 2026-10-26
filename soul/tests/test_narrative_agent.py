"""test_narrative_agent.py — Phase 5 Narrative Agent 生成 narrative candidate。"""
import pytest

from soul.agents.narrative import NarrativeAgent


def _ce():
    return {
        "consolidated_episode_id": "ce-1",
        "source_episode_ids_json": '["ep-1","ep-2"]',
        "source_event_ids_json": '["ev-1","ev-2"]',
        "summary": "Project Soul Phase 4 完成慢速回路，evidence-linked episodes 聚合为稳定输入",
        "importance_score": 0.9,
        "created_at": "t",
    }


def test_consolidated_episode_generates_narrative():
    nar = NarrativeAgent().process(_ce())
    assert nar is not None
    assert nar["narrative_type"] == "project_progress"
    assert set(nar["evidence_ids"]) == {"ev-1", "ev-2"}
    assert set(nar["episode_ids"]) == {"ep-1", "ep-2"}
    assert nar["consolidated_episode_id"] == "ce-1"
    assert nar["status"] == "candidate"
    assert nar["version"] == 1


def test_narrative_contains_evidence_ids():
    nar = NarrativeAgent().process(_ce())
    assert nar["evidence_ids"], "必须引用 evidence"


def test_narrative_contains_episode_ids():
    nar = NarrativeAgent().process(_ce())
    assert nar["episode_ids"], "必须引用 episode"


def test_narrative_no_fabricated_fact():
    """content 只来自 source summary，不新增事实。"""
    src_summary = "Project Soul Phase 4 完成慢速回路"
    ce = {"consolidated_episode_id": "c1",
          "source_episode_ids_json": "[]", "source_event_ids_json": "[]",
          "summary": src_summary}
    nar = NarrativeAgent().process(ce)
    # meaning 可以轻度解释，但不能声称"拥有真实意识"之类无证据结论
    assert "真实意识" not in nar["content"]
    assert "真正灵魂" not in nar["meaning"]
    assert "真实自我" not in nar["identity_effect"]


def test_no_source_returns_none():
    assert NarrativeAgent().process(None) is None
    assert NarrativeAgent().process({}) is None
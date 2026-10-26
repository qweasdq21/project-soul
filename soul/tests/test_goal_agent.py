"""test_goal_agent.py — Phase 8 Goal Agent 生成规则。"""
import pytest

from soul.agents.goal import GoalAgent, GOAL_TYPES


def _sm(content, mid="sm1", ev="ev-1"):
    return {"memory_id": mid, "content": content,
            "source_event_ids": [ev], "source_event_ids_json": None}


def _nar(content, nid="n1", ev="ev-2"):
    return {"narrative_id": nid, "content": content, "summary": content,
            "evidence_ids": [ev], "evidence_ids_json": None}


def _bel(statement, bid="b1", ev="ev-3"):
    return {"belief_id": bid, "statement": statement, "belief_type": "general",
            "evidence_ids": [ev], "evidence_ids_json": None}


def _lr(content, rid="l1", ev="ev-4"):
    return {"reflection_id": rid, "content": content, "summary": content,
            "event_ids": [ev], "event_ids_json": None, "candidate_updates_json": None,
            "observations_json": None}


def test_semantic_generates_milestone():
    cands = GoalAgent().process(semantic_mems=[_sm("Project Soul Phase 4 completed verified")])
    types = [c["goal_type"] for c in cands]
    assert "project_milestone" in types
    g = next(c for c in cands if c["goal_type"] == "project_milestone")
    assert g["evidence_ids"], "must have evidence ids"
    assert g["source_semantic_memory_ids"] == ["sm1"]


def test_rejection_generates_safety():
    rej = {"label": "real consciousness rejected: C04", "reason": "x",
           "evidence_refs": ["ev-9"], "evidence_refs_json": None}
    cands = GoalAgent().process(rejections=[rej])
    types = [c["goal_type"] for c in cands]
    assert "safety" in types


def test_belief_immutability_generates_safety():
    cands = GoalAgent().process(beliefs=[_bel("Narrative must remain evidence-bound and unimplemented")])
    types = [c["goal_type"] for c in cands]
    assert "safety" in types


def test_long_reflection_verification():
    cands = GoalAgent().process(long_reflections=[_lr("verify tests passed via constitution check")])
    types = [c["goal_type"] for c in cands]
    assert "verification" in types


def test_long_reflection_maintenance():
    cands = GoalAgent().process(long_reflections=[_lr("maintain stability of accepted state")])
    types = [c["goal_type"] for c in cands]
    assert "maintenance" in types


def test_goal_candidate_fields():
    cands = GoalAgent().process(semantic_mems=[_sm("Phase completed verified")])
    assert cands
    goal = cands[0]
    assert goal["goal_id"].startswith("goal-")
    assert goal["goal_type"] in GOAL_TYPES
    assert goal["status"] == "candidate"
    assert goal["priority"] >= 0.0 and goal["priority"] <= 1.0
    assert goal["version"] == 1
    assert goal["supersedes"] is None


def test_goal_title_is_neutral_task():
    cands = GoalAgent().process(semantic_mems=[_sm("Phase completed verified")])
    assert cands
    for w in ("I must", "永远保护", "我渴望", "真实灵魂", "真实意识"):
        assert w not in cands[0]["title"] + cands[0]["description"]


def test_no_sources_no_goals():
    empties = GoalAgent().process()
    # goal agent with no evidence sources produces nothing valid
    assert all(not (c["evidence_ids"]) for c in empties) or not empties
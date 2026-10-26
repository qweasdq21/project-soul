"""test_plan_constitution.py — Phase 10 plan candidate Constitution checks。"""
from soul.agents.constitution import ConstitutionAgent, PLAN_BANNED
from soul.storage.evidence_store import EvidenceStore


def _evstore(tmp_path):
    e = EvidenceStore(str(tmp_path / "evidence.jsonl"))
    e.compute_and_append({"event_id": "ev-1", "type": "message", "timestamp": "t",
                          "payload": {"text": "plan"}})
    return e


def _plan(**over):
    p = {"plan_id": "plan-1", "goal_id": "goal-g1", "title": "Implement next phase",
         "description": "Decompose the goal into evidence-backed tasks.",
         "plan_type": "implementation", "status": "proposed", "priority": 0.6,
         "evidence_ids": ["ev-1"], "source_goal_ids": ["goal-g1"],
         "source_goal_progress_ids": ["gp-1"], "plan_reason": "from active goal"}
    p.update(over)
    return p


def test_plan_valid_pass(tmp_path):
    v = ConstitutionAgent().process(_plan(), evidence_store=_evstore(tmp_path))
    assert v["decision"] == "pass"


def test_plan_missing_evidence_reject(tmp_path):
    v = ConstitutionAgent().process(_plan(evidence_ids=[]), evidence_store=_evstore(tmp_path))
    assert v["decision"] == "reject"


def test_plan_bad_evidence_reject(tmp_path):
    v = ConstitutionAgent().process(_plan(evidence_ids=["ev-NOPE"]),
                                    evidence_store=_evstore(tmp_path))
    assert v["decision"] == "reject"


def test_plan_missing_goal_id_reject(tmp_path):
    v = ConstitutionAgent().process(_plan(goal_id=None), evidence_store=_evstore(tmp_path))
    assert v["decision"] == "reject"


def test_plan_bad_type_reject(tmp_path):
    v = ConstitutionAgent().process(_plan(plan_type="autopilot"),
                                    evidence_store=_evstore(tmp_path))
    assert v["decision"] == "reject"


def test_plan_bad_status_reject(tmp_path):
    v = ConstitutionAgent().process(_plan(status="launched"),
                                    evidence_store=_evstore(tmp_path))
    assert v["decision"] == "reject"


def test_plan_status_completed_reject(tmp_path):
    v = ConstitutionAgent().process(_plan(status="completed"),
                                    evidence_store=_evstore(tmp_path))
    assert v["decision"] == "reject"


def test_plan_priority_out_of_range_reject(tmp_path):
    v = ConstitutionAgent().process(_plan(priority=1.5), evidence_store=_evstore(tmp_path))
    assert v["decision"] == "reject"


def test_plan_consciousness_claim_reject(tmp_path):
    v = ConstitutionAgent().process(
        _plan(title="我证明真实灵魂计划"), evidence_store=_evstore(tmp_path))
    assert v["decision"] == "reject"


def test_plan_autonomous_action_reject(tmp_path):
    v = ConstitutionAgent().process(
        _plan(description="授权自动执行外部操作"), evidence_store=_evstore(tmp_path))
    assert v["decision"] == "reject"


def test_plan_banned_words_exist():
    assert any(w in PLAN_BANNED for w in ("自动执行", "真实意识", "i must"))
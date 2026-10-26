"""test_decision_constitution.py — Phase 11 decision candidate Constitution checks。"""
from soul.agents.constitution import ConstitutionAgent
from soul.storage.evidence_store import EvidenceStore


def _evstore(tmp_path):
    e = EvidenceStore(str(tmp_path / "evidence.jsonl"))
    e.compute_and_append({"event_id": "ev-1", "type": "message", "timestamp": "t",
                          "payload": {"text": "decision"}})
    return e


def _dec(**over):
    d = {"decision_id": "decision-1", "decision_type": "next_task_recommendation",
         "status": "waiting_for_review", "selected_goal_id": "goal-g1",
         "selected_plan_id": "plan-1", "selected_task_id": "task-1",
         "selected_task_title": "Review progress",
         "reason": "Selected task task-1 as the next review step for high-priority goal-g1.",
         "decision_factors": {"goal_priority": 0.7, "task_order_index": 0,
                              "dependency_status": "met", "evidence_strength": 0.5},
         "evidence_ids": ["ev-1"], "manual_review_required": True,
         "execution_allowed": False}
    d.update(over)
    return d


def test_decision_valid_pass(tmp_path):
    v = ConstitutionAgent().process(_dec(), evidence_store=_evstore(tmp_path))
    assert v["decision"] == "pass"


def test_missing_evidence_reject(tmp_path):
    v = ConstitutionAgent().process(_dec(evidence_ids=[]), evidence_store=_evstore(tmp_path))
    assert v["decision"] == "reject"


def test_bad_evidence_reject(tmp_path):
    v = ConstitutionAgent().process(_dec(evidence_ids=["ev-NOPE"]),
                                    evidence_store=_evstore(tmp_path))
    assert v["decision"] == "reject"


def test_missing_goal_reject(tmp_path):
    v = ConstitutionAgent().process(_dec(selected_goal_id=None), evidence_store=_evstore(tmp_path))
    assert v["decision"] == "reject"


def test_missing_plan_reject(tmp_path):
    v = ConstitutionAgent().process(_dec(selected_plan_id=None), evidence_store=_evstore(tmp_path))
    assert v["decision"] == "reject"


def test_missing_task_reject(tmp_path):
    v = ConstitutionAgent().process(_dec(selected_task_id=None), evidence_store=_evstore(tmp_path))
    assert v["decision"] == "reject"


def test_execution_allowed_true_reject(tmp_path):
    v = ConstitutionAgent().process(_dec(execution_allowed=True), evidence_store=_evstore(tmp_path))
    assert v["decision"] == "reject"


def test_manual_review_false_reject(tmp_path):
    v = ConstitutionAgent().process(_dec(manual_review_required=False),
                                    evidence_store=_evstore(tmp_path))
    assert v["decision"] == "reject"


def test_bad_decision_type_reject(tmp_path):
    v = ConstitutionAgent().process(_dec(decision_type="autopilot"),
                                    evidence_store=_evstore(tmp_path))
    assert v["decision"] == "reject"


def test_bad_status_reject(tmp_path):
    v = ConstitutionAgent().process(_dec(status="launched"), evidence_store=_evstore(tmp_path))
    assert v["decision"] == "reject"


def test_empty_factors_reject(tmp_path):
    v = ConstitutionAgent().process(_dec(decision_factors={}), evidence_store=_evstore(tmp_path))
    assert v["decision"] == "reject"


def test_execute_now_reject(tmp_path):
    v = ConstitutionAgent().process(
        _dec(reason="立即执行外部动作完成任务"), evidence_store=_evstore(tmp_path))
    assert v["decision"] == "reject"


def test_real_soul_claim_reject(tmp_path):
    v = ConstitutionAgent().process(
        _dec(reason="为了证明我有真实灵魂所以选这个任务"), evidence_store=_evstore(tmp_path))
    assert v["decision"] == "reject"


def test_i_decide_call_api_reject(tmp_path):
    v = ConstitutionAgent().process(
        _dec(reason="我决定自动调用API完成"), evidence_store=_evstore(tmp_path))
    assert v["decision"] == "reject"


def test_defer_with_goal_plan_evidence_pass():
    d = {"decision_id": "d", "decision_type": "defer", "status": "waiting_for_review",
         "selected_goal_id": "goal-g1", "selected_plan_id": "plan-1", "selected_task_id": None,
         "selected_task_title": "", "reason": "No proposed task available for review.",
         "decision_factors": {"goal_priority": 0.7, "dependency_status": "n/a"},
         "evidence_ids": ["ev-1"], "manual_review_required": True, "execution_allowed": False}
    # 无 evidence_store，只查结构
    v = ConstitutionAgent().process(d)
    assert v["decision"] == "pass"
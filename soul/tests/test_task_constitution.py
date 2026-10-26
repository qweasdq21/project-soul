"""test_task_constitution.py — Phase 10 task candidate Constitution checks。"""
from soul.agents.constitution import ConstitutionAgent, TASK_BANNED
from soul.storage.evidence_store import EvidenceStore


def _evstore(tmp_path):
    e = EvidenceStore(str(tmp_path / "evidence.jsonl"))
    e.compute_and_append({"event_id": "ev-1", "type": "message", "timestamp": "t",
                          "payload": {"text": "task"}})
    return e


def _task(**over):
    t = {"task_id": "task-1", "plan_id": "plan-1", "goal_id": "goal-g1",
         "title": "Review verified goal progress", "description": "Inspect current progress.",
         "task_type": "inspect", "status": "proposed", "order_index": 0, "priority": 0.6,
         "evidence_ids": ["ev-1"], "depends_on_task_ids": [], "expected_output": "summary",
         "execution_mode": "manual_only"}
    t.update(over)
    return t


def test_task_valid_pass(tmp_path):
    v = ConstitutionAgent().process(_task(), evidence_store=_evstore(tmp_path))
    assert v["decision"] == "pass"


def test_task_missing_evidence_reject(tmp_path):
    v = ConstitutionAgent().process(_task(evidence_ids=[]), evidence_store=_evstore(tmp_path))
    assert v["decision"] == "reject"


def test_task_missing_plan_id_reject(tmp_path):
    v = ConstitutionAgent().process(_task(plan_id=None), evidence_store=_evstore(tmp_path))
    assert v["decision"] == "reject"


def test_task_missing_goal_id_reject(tmp_path):
    v = ConstitutionAgent().process(_task(goal_id=None), evidence_store=_evstore(tmp_path))
    assert v["decision"] == "reject"


def test_task_bad_type_reject(tmp_path):
    v = ConstitutionAgent().process(_task(task_type="execute"),
                                    evidence_store=_evstore(tmp_path))
    assert v["decision"] == "reject"


def test_task_bad_status_reject(tmp_path):
    v = ConstitutionAgent().process(_task(status="launched"),
                                    evidence_store=_evstore(tmp_path))
    assert v["decision"] == "reject"


def test_task_status_completed_candidate_reject(tmp_path):
    v = ConstitutionAgent().process(_task(status="completed_candidate"),
                                    evidence_store=_evstore(tmp_path))
    assert v["decision"] == "reject"


def test_task_bad_execution_mode_reject(tmp_path):
    v = ConstitutionAgent().process(_task(execution_mode="auto"),
                                    evidence_store=_evstore(tmp_path))
    assert v["decision"] == "reject"


def test_task_send_email_reject(tmp_path):
    v = ConstitutionAgent().process(
        _task(description="发送邮件给用户"), evidence_store=_evstore(tmp_path))
    assert v["decision"] == "reject"


def test_task_call_api_reject(tmp_path):
    v = ConstitutionAgent().process(
        _task(title="调用API获取数据"), evidence_store=_evstore(tmp_path))
    assert v["decision"] == "reject"


def test_task_modify_file_reject(tmp_path):
    v = ConstitutionAgent().process(
        _task(description="修改配置文件"), evidence_store=_evstore(tmp_path))
    assert v["decision"] == "reject"


def test_task_execute_external_reject(tmp_path):
    v = ConstitutionAgent().process(
        _task(description="立即执行外部操作系统命令"), evidence_store=_evstore(tmp_path))
    assert v["decision"] == "reject"


def test_task_banned_words_exist():
    assert any(w in TASK_BANNED for w in ("发送邮件", "调用API", "修改文件", "后台运行"))
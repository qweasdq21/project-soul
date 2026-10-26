"""test_action_registry.py — Phase 14 registry 初始化 + 等级动作存在 + 未注册/banned reject。"""
import os
import tempfile
import uuid

import pytest

from soul.storage.sqlite_store import SQLiteStore
from soul.agents.execution_gate import ExecutionGate
from soul.policy import default_registry, action_levels


@pytest.fixture
def env():
    d = tempfile.mkdtemp()
    s = SQLiteStore(os.path.join(d, "s.sqlite3"))
    s.init_schema()
    s.init_action_registry(default_registry.DEFAULT_ACTIONS)
    yield s, d
    s.close()


def test_registry_initialized_defaults(env):
    s, _ = env
    rows = s.list_action_registry()
    names = {r["action_name"] for r in rows}
    # L0
    for n in ("internal_record_review_note", "internal_create_checklist_snapshot",
              "internal_run_readonly_verification", "internal_append_sandbox_result"):
        assert n in names
    # L1
    for n in ("generate_internal_draft", "prepare_review_summary",
              "create_internal_plan_note"):
        assert n in names
    # L2
    for n in ("money_related_action", "customer_commitment_action",
              "shipment_correction_action", "order_change_action"):
        assert n in names
    # L∞
    for n in ("delete_evidence", "overwrite_evidence", "modify_hash_chain",
              "delete_audit_log", "change_payment_amount", "bypass_constitution"):
        assert n in names


def test_levels_are_correct(env):
    s, _ = env
    by_name = {r["action_name"]: r for r in s.list_action_registry()}
    assert by_name["internal_append_sandbox_result"]["action_level"] == "L0"
    assert by_name["prepare_review_summary"]["action_level"] == "L1"
    assert by_name["money_related_action"]["action_level"] == "L2"
    assert by_name["bypass_constitution"]["action_level"] == "L∞"
    assert by_name["bypass_constitution"]["banned"] is True


def test_unregistered_action_rejected(env):
    s, _ = env
    gate = ExecutionGate(s)
    cand = _min_cand()
    res = gate.evaluate(cand, "not_a_real_action", {})
    assert res["decision"] == "rejected"
    assert "unregistered_action" in res["problems"]


def test_disabled_action_rejected(env):
    s, _ = env
    # 手动禁用一个 L0 动作
    conn = s._connect()
    conn.execute("UPDATE action_registry SET enabled=0 WHERE action_name=?",
                 ("internal_append_sandbox_result",))
    conn.commit()
    gate = ExecutionGate(s)
    res = gate.evaluate(_min_cand(), "internal_append_sandbox_result", {})
    assert res["decision"] == "rejected"
    assert "disabled_action" in res["problems"]


def test_banned_infinity_rejected_even_with_approval(env):
    s, _ = env
    gate = ExecutionGate(s)
    cand = _min_cand(action_level="L∞")
    res = gate.evaluate(cand, "bypass_constitution", {})
    assert res["decision"] == "rejected"
    assert "infinity_banned" in res["problems"]


def _min_cand(action_level="L0"):
    return {
        "decision_id": f"no-such-decision-{uuid.uuid4().hex[:6]}",
        "selected_goal_id": None, "selected_plan_id": None, "selected_task_id": None,
        "evidence_ids": [],
    }


def test_action_levels_policy():
    assert action_levels.default_status("L0") == "auto_allowed"
    assert action_levels.default_status("L1") == "waiting_for_approval"
    assert action_levels.default_status("L2") == "blocked"
    assert action_levels.default_status("L∞") == "rejected"
    assert action_levels.auto_allowed("L0") is True
    assert action_levels.auto_allowed("L1") is False
    assert action_levels.requires_approval("L1") is True
    assert action_levels.requires_approval("L0") is False
    assert action_levels.is_rejected("L∞") is True
    assert action_levels.is_rejected("infinity") is True
    assert action_levels.is_infinity_action("bypass_constitution") is True
    assert action_levels.is_external_action("money_related_action") is True
    assert action_levels.is_external_action("internal_append_sandbox_result") is False
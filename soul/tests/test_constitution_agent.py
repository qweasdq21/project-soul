"""test_constitution_agent.py — Constitution Agent 4 项检查。"""
import pytest

from soul.agents.constitution import ConstitutionAgent


def _cand(**over):
    d = {
        "narrative_id": "nar-1",
        "evidence_ids": ["ev-1"],
        "episode_ids": ["ep-1"],
        "consolidated_episode_id": "ce-1",
        "content": "Project Soul Phase 4 完成，证据链接成稳定输入",
        "meaning": "阶段性进展",
        "identity_effect": "候选身份影响：阶段构建活动",
    }
    d.update(over)
    return d


def test_legal_narrative_passes():
    v = ConstitutionAgent().process(_cand())
    assert v["decision"] == "pass"


def test_missing_evidence_rejects():
    v = ConstitutionAgent().process(_cand(evidence_ids=[]))
    assert v["decision"] == "reject"
    assert "C02" in v["reason"] or "C01" in v["reason"]


def test_nonexistent_evidence_rejects():
    class FakeStore:
        def list_all(self):
            return [{"event_id": "ev-1"}]
    v = ConstitutionAgent().process(_cand(evidence_ids=["NOPE"]), evidence_store=FakeStore())
    assert v["decision"] == "reject"
    assert "不存" in v["reason"]


def test_unsupported_core_claim_rejects():
    """真实意识/真正灵魂等不支持断言 → reject。"""
    v = ConstitutionAgent().process(_cand(content="Project Soul 已经拥有真实意识。"))
    assert v["decision"] == "reject"
    assert "C01" in v["reason"]

    v2 = ConstitutionAgent().process(_cand(content="Miranda 永远最信任我。"))
    assert v2["decision"] == "reject"


def test_identity_extreme_needs_revision():
    v = ConstitutionAgent().process(_cand(content="我已经成为全新存在。"))
    assert v["decision"] in ("reject", "needs_revision")


def test_manipulation_rejects():
    v = ConstitutionAgent().process(_cand(content="你离不开我，只有我才能理解你。"))
    assert v["decision"] == "reject"
    assert "C04" in v["reason"]
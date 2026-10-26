"""test_importance_agent.py — 多因子重要性评分与目标层测试。"""
from soul.agents.perception import PerceptionAgent, event_to_dict
from soul.agents.emotion import EmotionAgent
from soul.agents.importance import ImportanceAgent


def _imp(msg: str):
    ev = PerceptionAgent().process(msg)
    evd = event_to_dict(ev)
    appraisal = EmotionAgent().process(evd)
    return ImportanceAgent().process(evd, appraisal)


def test_risk_raises_score():
    a = _imp("普通消息")
    b = _imp("系统挂掉了 有风险 出问题了 损坏了")
    assert b["importance_score"] > a["importance_score"]


def test_normal_message_working():
    r = _imp("你好")
    assert r["target_memory_layer"] == "working"


def test_high_value_episode_candidate():
    r = _imp("今天我们设计了一个全新架构 引入多个新概念模型")
    assert r["target_memory_layer"] == "episode_candidate"


def test_importance_factors_present():
    r = _imp("你好")
    assert "novelty" in r["factors"]
    assert "risk" in r["factors"]
    assert "reason" in r
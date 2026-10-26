"""test_emotion_agent.py — 8 维工程情绪向量规则测试。"""
from soul.agents.emotion import EmotionAgent, EMOTION_DIMS


def _app(msg: str):
    from soul.agents.perception import PerceptionAgent, event_to_dict
    ev = PerceptionAgent().process(msg)
    return EmotionAgent().process(event_to_dict(ev))


def test_8_dims():
    r = _app("hello")
    assert set(r["vector"].keys()) == set(EMOTION_DIMS)


def test_values_in_01():
    r = _app("hello")
    for v in r["vector"].values():
        assert 0.0 <= v <= 1.0


def test_risk_message_high_risk_stress():
    r = _app("系统挂掉了 有风险 出问题了")
    assert r["vector"]["risk"] >= 0.5
    assert r["vector"]["stress"] >= 0.3


def test_question_message_high_curiosity():
    r = _app("这个架构为什么这样设计？")
    assert r["vector"]["curiosity"] >= 0.5
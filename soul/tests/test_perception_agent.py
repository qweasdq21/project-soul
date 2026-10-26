"""test_perception_agent.py — Perception Agent 生成 Event 的测试。"""
import pytest

from soul.agents.perception import PerceptionAgent


def _ev():
    return PerceptionAgent().process("  你好World  ")


def test_generates_event_with_id():
    e = _ev()
    assert e.event_id
    assert len(e.event_id) > 0


def test_raw_content_preserved():
    e = _ev()
    assert e.raw_content == "  你好World  "


def test_normalized_content():
    e = _ev()
    assert e.normalized_content == "你好World"


def test_source_actor_event_type():
    e = _ev()
    assert e.source == "cli"
    assert e.actor == "user"
    assert e.event_type == "user_message"


def test_metadata_default():
    e = _ev()
    assert e.metadata == {}
"""Orchestrator Agent — 协调所有子 Agent，控制 Fast/Slow 双回路，维护全局循环。"""
from __future__ import annotations
from soul.agents.base import BaseAgent


class OrchestratorAgent(BaseAgent):
    """输入: 用户消息 / 系统事件 / 心跳
    输出: Fast 或 Slow 回路执行指令
    Phase 2+ 实现：调度、状态位图、回路分发。
    """
    name = "orchestrator"

    def process(self, input: object) -> object:
        # Phase 2+ 实现
        raise NotImplementedError
"""运行时上下文占位。Phase 2+ 承载 agents 实例、store 引用、全局状态。"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class RuntimeContext:
    """各 Agent 与 Store 共享的运行时上下文。

    Phase 1 仅占位；Phase 2+ 填充真正的 store / agent 实例。
    """
    stores: dict[str, object] = field(default_factory=dict)
    agents: dict[str, object] = field(default_factory=dict)
    state: dict[str, object] = field(default_factory=dict)

    def register_store(self, name: str, store: object) -> None:
        self.stores[name] = store

    def register_agent(self, name: str, agent: object) -> None:
        self.agents[name] = agent
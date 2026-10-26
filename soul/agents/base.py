"""Agent 基类。约定统一接口。

Phase 1 仅定义接口约定与空实现；各 Agent 在后续阶段填充 `process`。
"""
from __future__ import annotations
from typing import Any


class BaseAgent:
    """所有 Agent 的基类。

    统一约定：
        process(input: Any) -> Any
    每个子类 override。input/output 类型在每个 Agent 的 docstring 中声明。
    """

    name: str = "base"

    def process(self, input: Any) -> Any:
        raise NotImplementedError(f"{self.name}.process not implemented")

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name}>"
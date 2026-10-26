"""存储接口基类。所有 Store 实现统一接口。

Phase 1 仅定义契约；Phase 2+ 提供具体实现。
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any


class BaseStore(ABC):
    """持久化接口。

    - append_writes_generated: 该类存储是否为"只追加"不可变层
    - write(obj): 写入一个对象
    - read(obj_id): 按 id 读回
    - list_all(): 列出全部
    """

    append_only: bool = False

    @abstractmethod
    def write(self, obj: Any) -> str:
        """写入并返回 id。"""
        ...

    @abstractmethod
    def read(self, obj_id: str) -> Any | None:
        ...

    @abstractmethod
    def list_all(self) -> list[Any]:
        ...
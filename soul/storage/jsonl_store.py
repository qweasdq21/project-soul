"""JSONLStore — 通用 JSONL 追加存储。

只追加（append-only），每行一个 JSON 对象。不提供 update/delete。
"""
from __future__ import annotations
import json
from typing import Any, Iterator

from soul.storage.base import BaseStore


class JSONLStore(BaseStore):
    append_only = True

    def __init__(self, path: str):
        self.path = path

    def write(self, obj: dict[str, Any]) -> str:
        """追加写入一条记录，返回其 id（若有），否则返回行号字符串。"""
        # 规范化：稳定排序保证可复现
        line = json.dumps(obj, ensure_ascii=False, sort_keys=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        _id = obj.get("event_id") or obj.get("id") or ""
        return str(_id) if _id else str(self.count() - 1)

    def read(self, obj_id: str) -> dict[str, Any] | None:
        for obj in self.iter_records():
            if obj.get("event_id") == obj_id or obj.get("id") == obj_id:
                return obj
        return None

    def iter_records(self) -> Iterator[dict[str, Any]]:
        try:
            with open(self.path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        yield json.loads(line)
        except FileNotFoundError:
            return

    def list_all(self) -> list[dict[str, Any]]:
        return list(self.iter_records())

    def count(self) -> int:
        return sum(1 for _ in self.iter_records())
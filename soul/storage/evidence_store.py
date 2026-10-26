"""EvidenceStore — 不可变证据层（JSONL, append-only），带 hash chain 防篡改。

Constitution 01：只允许追加，禁止修改/删除。
hash = sha256(canonical_event_without_hash + previous_hash)
第一条 event 的 previous_hash = None。

verify_chain() 逐条校验：
  - previous_hash 是否等于上一条的 hash
  - 当前 hash 是否等于重新计算的 hash
"""
from __future__ import annotations
import hashlib
import json
from typing import Any

from soul.storage.jsonl_store import JSONLStore


def _canonical_json(obj: dict[str, Any]) -> str:
    """稳定序列化（sort_keys + ensure_ascii=False + 紧凑分隔），保证 hash 可复现。"""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _compute_hash(obj_unhashed: dict[str, Any], previous_hash: str | None) -> str:
    """计算 event hash：sha256(规范化无 hash 内容 + previous_hash)。"""
    canonical = _canonical_json(obj_unhashed)
    data = (canonical + (previous_hash or "")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


class EvidenceStore:
    """不可变证据追加存储 + hash chain 校验。"""

    append_only = True

    def __init__(self, path: str):
        self.jsonl = JSONLStore(path)

    def append(
        self,
        event: dict[str, Any],
    ) -> dict[str, Any]:
        """追加一条 Event（其内部已含 event_id/hash/previous_hash）。"""
        # 校验 event 必须具备的关键字段
        missing = [k for k in ("event_id", "hash") if event.get(k) is None]
        if missing:
            raise ValueError(f"event missing required field(s): {missing}")

        # 读取上一条 hash 作为 previous_hash
        prev = self.last()
        previous_hash = prev["hash"] if prev else None
        if event.get("previous_hash") is None:
            event["previous_hash"] = previous_hash

        self.jsonl.write(event)
        return event

    def compute_and_append(
        self,
        base_event: dict[str, Any],
    ) -> dict[str, Any]:
        """基于无 hash 的 event 计算 hash chain 并追加。Phase 2 主入口。"""
        prev = self.jsonl.list_all()
        previous_hash = prev[-1]["hash"] if prev else None
        unhashed = dict(base_event)
        unhashed["previous_hash"] = previous_hash
        unhashed.pop("hash", None)
        event_hash = _compute_hash(unhashed, previous_hash)
        event = dict(unhashed)
        event["hash"] = event_hash
        self.jsonl.write(event)
        return event

    def last(self) -> dict[str, Any] | None:
        recs = self.jsonl.list_all()
        return recs[-1] if recs else None

    def list_all(self) -> list[dict[str, Any]]:
        return self.jsonl.list_all()

    def read(self, event_id: str) -> dict[str, Any] | None:
        return self.jsonl.read(event_id)

    def count(self) -> int:
        return self.jsonl.count()

    def verify_chain(self) -> tuple[bool, str]:
        """逐条验证 hash chain。

        返回 (valid, message)。message 描述结果或失败位置/原因。
        """
        recs = self.jsonl.list_all()
        if not recs:
            return True, "Evidence chain valid. Total events: 0"

        for i, rec in enumerate(recs, start=1):
            expected_prev = (recs[i - 2]["hash"] if i >= 2 else None)
            if rec.get("previous_hash") != expected_prev:
                return False, (
                    f"Evidence chain invalid.\n"
                    f"Failed at line {i}.\n"
                    f"Reason: previous_hash mismatch. "
                    f"got {rec.get('previous_hash')!r}, expected {expected_prev!r}"
                )
            # 重算当前 hash
            unhashed = dict(rec)
            h = unhashed.pop("hash", None)
            recomputed = _compute_hash(unhashed, expected_prev)
            if recomputed != h:
                return False, (
                    f"Evidence chain invalid.\n"
                    f"Failed at line {i}.\n"
                    f"Reason: hash mismatch."
                )
        return True, f"Evidence chain valid.\nTotal events: {len(recs)}"
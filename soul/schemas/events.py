"""Event / Evidence — 不可变事实层。

只允许追加；hash = hash(本体 + previous_hash) 链式防篡改。
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Event:
    event_id: str
    timestamp: str                      # ISO 8601
    source: str                         # 来源：perception / tool / system ...
    actor: str                          # 谁发起（user / agent / system）
    event_type: str
    raw_content: str
    normalized_content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    hash: str = ""
    previous_hash: Optional[str] = None
    created_at: str = ""
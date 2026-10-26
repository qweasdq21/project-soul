"""Importer — 未来从真实 Hermes 对话历史导入 event 的接口占位。

Phase 1 不接真实历史（用户已确认）。Phase 7+ 实现。
"""
from __future__ import annotations


class EventImporter:
    """预留接口：把外部对话历史转成 event 流。

    Phase 1 不做任何实现，仅声明接口契约，避免日后污染项目形状。
    """

    def import_events(self, source: str) -> list[object]:
        raise NotImplementedError  # Phase 7 实现
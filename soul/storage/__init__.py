"""storage — 存储层。

- evidence: JSONL 不可变追加（真正实现在 Phase 2）
- 结构化状态: SQLite（真正实现在 Phase 3+）
- importer: 未来从真实 Hermes 对话导入 event（接口占位）

Phase 1 仅接口 + 空桩。
"""
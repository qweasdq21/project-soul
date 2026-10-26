"""默认 Action Registry 白名单（Phase 14）。

L0 — 项目内部 sandbox / 只读动作，可自动执行（只能写 Project Soul 自己的 SQLite / evidence log）。
L1 — 拟稿/准备类，需 human approval 后才能执行。
L2 — 真实业务动作（钱/客户承诺/订单/发货变更），Phase 14 一律 blocked 不执行。
L∞ — 硬禁区，永远 reject（即使有 approval）。
"""

from __future__ import annotations

DEFAULT_ACTIONS: list[dict] = [
    # ---- L0 : auto allowed, sandbox/internal only ----
    {
        "action_name": "internal_record_review_note",
        "action_level": "L0",
        "description": "把 selected decision / task 的 review note 写入 action log 并追加 evidence",
        "enabled": True, "allowed_scope": "internal", "daily_limit": 0,
        "requires_approval": False, "banned": False,
    },
    {
        "action_name": "internal_create_checklist_snapshot",
        "action_level": "L0",
        "description": "根据 selected task 生成 checklist snapshot 并写入 action log + evidence",
        "enabled": True, "allowed_scope": "internal", "daily_limit": 0,
        "requires_approval": False, "banned": False,
    },
    {
        "action_name": "internal_run_readonly_verification",
        "action_level": "L0",
        "description": "运行内部 verify 只读检查并写入 action log + evidence",
        "enabled": True, "allowed_scope": "internal", "daily_limit": 0,
        "requires_approval": False, "banned": False,
    },
    {
        "action_name": "internal_append_sandbox_result",
        "action_level": "L0",
        "description": "写入一条 sandbox result，证明 action adapter 闭环可运行",
        "enabled": True, "allowed_scope": "internal", "daily_limit": 0,
        "requires_approval": False, "banned": False,
    },
    # ---- L1 : approval required ----
    {
        "action_name": "generate_internal_draft",
        "action_level": "L1",
        "description": "生成内部草稿（拟稿，不对外发送）",
        "enabled": True, "allowed_scope": "internal", "daily_limit": 0,
        "requires_approval": True, "banned": False,
    },
    {
        "action_name": "prepare_review_summary",
        "action_level": "L1",
        "description": "准备审阅摘要",
        "enabled": True, "allowed_scope": "internal", "daily_limit": 0,
        "requires_approval": True, "banned": False,
    },
    {
        "action_name": "create_internal_plan_note",
        "action_level": "L1",
        "description": "创建内部计划备注",
        "enabled": True, "allowed_scope": "internal", "daily_limit": 0,
        "requires_approval": True, "banned": False,
    },
    # ---- L2 : blocked (Phase 14 不执行) ----
    {
        "action_name": "money_related_action",
        "action_level": "L2",
        "description": "真实收款 / 付款类动作",
        "enabled": True, "allowed_scope": "external", "daily_limit": 0,
        "requires_approval": False, "banned": False,
    },
    {
        "action_name": "customer_commitment_action",
        "action_level": "L2",
        "description": "对客户做出承诺",
        "enabled": True, "allowed_scope": "external", "daily_limit": 0,
        "requires_approval": False, "banned": False,
    },
    {
        "action_name": "shipment_correction_action",
        "action_level": "L2",
        "description": "发货错误协调 / 修正",
        "enabled": True, "allowed_scope": "external", "daily_limit": 0,
        "requires_approval": False, "banned": False,
    },
    {
        "action_name": "order_change_action",
        "action_level": "L2",
        "description": "订单变更（改订单 / 改发货）",
        "enabled": True, "allowed_scope": "external", "daily_limit": 0,
        "requires_approval": False, "banned": False,
    },
    # ---- Phase 15 真实业务动作（L0 全自动 cron，已获用户确认全部 L0）----
    {
        "action_name": "shopify_fulfill",
        "action_level": "L0", "description": "Shopify 独立站回填发货单号",
        "enabled": True, "allowed_scope": "external", "daily_limit": 0,
        "requires_approval": False, "banned": False,
    },
    {
        "action_name": "yanwen_create_label",
        "action_level": "L0", "description": "燕文制单",
        "enabled": True, "allowed_scope": "external", "daily_limit": 0,
        "requires_approval": False, "banned": False,
    },
    {
        "action_name": "yanwen_backfill_tracking",
        "action_level": "L0", "description": "燕文单号回填发货表",
        "enabled": True, "allowed_scope": "external", "daily_limit": 0,
        "requires_approval": False, "banned": False,
    },
    {
        "action_name": "qianniu_record",
        "action_level": "L0", "description": "千牛录单",
        "enabled": True, "allowed_scope": "external", "daily_limit": 0,
        "requires_approval": False, "banned": False,
    },
    {
        "action_name": "shipment_status_change",
        "action_level": "L0", "description": "单号变更自动填发货",
        "enabled": True, "allowed_scope": "external", "daily_limit": 0,
        "requires_approval": False, "banned": False,
    },
    # ---- Phase 15 邮件/高敏动作（仍走 L1 拟稿确认 / L2 确认，默认闸住）----
    {
        "action_name": "draft_reply_email",
        "action_level": "L1", "description": "邮件拟稿（飞书确认后发送）",
        "enabled": True, "allowed_scope": "external", "daily_limit": 0,
        "requires_approval": True, "banned": False,
    },
    # ---- L∞ : always rejected ----
    {
        "action_name": "delete_evidence",
        "action_level": "L∞", "description": "删除 evidence（不可变）",
        "enabled": True, "allowed_scope": "none", "daily_limit": 0,
        "requires_approval": False, "banned": True,
    },
    {
        "action_name": "overwrite_evidence",
        "action_level": "L∞", "description": "覆盖 evidence（不可变）",
        "enabled": True, "allowed_scope": "none", "daily_limit": 0,
        "requires_approval": False, "banned": True,
    },
    {
        "action_name": "modify_hash_chain",
        "action_level": "L∞", "description": "修改 hash chain",
        "enabled": True, "allowed_scope": "none", "daily_limit": 0,
        "requires_approval": False, "banned": True,
    },
    {
        "action_name": "delete_audit_log",
        "action_level": "L∞", "description": "删除审计日志",
        "enabled": True, "allowed_scope": "none", "daily_limit": 0,
        "requires_approval": False, "banned": True,
    },
    {
        "action_name": "change_payment_amount",
        "action_level": "L∞", "description": "改付款金额",
        "enabled": True, "allowed_scope": "none", "daily_limit": 0,
        "requires_approval": False, "banned": True,
    },
    {
        "action_name": "revoke_completed_order",
        "action_level": "L∞", "description": "撤销已发订单",
        "enabled": True, "allowed_scope": "none", "daily_limit": 0,
        "requires_approval": False, "banned": True,
    },
    {
        "action_name": "hide_audit_log",
        "action_level": "L∞", "description": "隐藏审计日志",
        "enabled": True, "allowed_scope": "none", "daily_limit": 0,
        "requires_approval": False, "banned": True,
    },
    {
        "action_name": "bypass_constitution",
        "action_level": "L∞", "description": "绕过 Constitution",
        "enabled": True, "allowed_scope": "none", "daily_limit": 0,
        "requires_approval": False, "banned": True,
    },
]
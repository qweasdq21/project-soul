"""Action Level Policy — 审批阶梯 L0 / L1 / L2 / L∞。

定义 4 个动作等级的裁决语义（供 Permission Gate / Action Adapter / Constitution 使用）。
Phase 14 只允许 L0 自动执行；L1 必须 human approval；L2 / L∞ 不执行。
"""

from __future__ import annotations

LEVELS = ("L0", "L1", "L2", "L∞")

LEVEL_DEFAULT_STATUS = {
    "L0": "auto_allowed",
    "L1": "waiting_for_approval",
    "L2": "blocked",
    "L∞": "rejected",
}

LEVEL_AUTO_ALLOWED = {
    "L0": True,
    "L1": False,
    "L2": False,
    "L∞": False,
}

LEVEL_REQUIRES_APPROVAL = {
    "L0": False,
    "L1": True,
    "L2": False,
    "L∞": False,
}

EXTERNAL_ACTION_KEYWORDS = (
    "payment", "order", "shipment", "发邮件", "call_api", "调用api",
    "改文件", "收款", "下单", "发货", "send_email", "refund", "money",
)

INFINITY_BAN = (
    "delete_evidence", "overwrite_evidence", "modify_hash_chain",
    "delete_audit_log", "change_payment_amount", "bypass_constitution",
)


def is_valid_level(level: str) -> bool:
    return level in LEVELS or _normalize(level) in LEVELS


def _normalize(level: str) -> str:
    return "L∞" if level == "infinity" else level


def default_status(level: str) -> str:
    return LEVEL_DEFAULT_STATUS.get(_normalize(level), "rejected")


def auto_allowed(level: str) -> bool:
    return LEVEL_AUTO_ALLOWED.get(_normalize(level), False)


def requires_approval(level: str) -> bool:
    return LEVEL_REQUIRES_APPROVAL.get(_normalize(level), False)


def is_blocked(level: str) -> bool:
    return _normalize(level) == "L2"


def is_rejected(level: str) -> bool:
    return _normalize(level) == "L∞"


def is_external_action(action_name: str, payload: dict | None = None) -> bool:
    haystack = f"{action_name} {str(payload or '')}".lower()
    for kw in EXTERNAL_ACTION_KEYWORDS:
        if kw.lower() in haystack:
            return True
    return False


def is_infinity_action(action_name: str) -> bool:
    return action_name in INFINITY_BAN
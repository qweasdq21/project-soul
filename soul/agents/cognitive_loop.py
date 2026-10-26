"""Cognitive Loop — LEBREW 监督脑（Phase 15 C 方案）。

职责：周期性醒来的「监督脑 + 异常闸 + 战略提炼器」。不接管 L0 真实动作执行
（那些由看门狗直接自动跑），只在每次醒来时：

1. 审计（audit）：读 action_logs，检测异常模式——
   - 高失败率（一小时内失败占比超阈值）
   - 动作超频（某动作在窗口内执行次数超 daily_limit）
   - 危险动作触碰（L∞ 动作被尝试 / blocked 记录）
2. 提炼（distill）：把 LEBREW 真实 evidence 喂给 belief/goal 提炼出战略方向摘要
   （只读，不修改外部世界）
3. 闸门（guard）：发现的异常写成 guard 记录（写 execution_requests 标记 L2，
   或立即上报摘要），供飞书供用户查看。

安全边界（C 方案）：本循环绝不执行真实业务动作、绝不改数据/钱/订单。
L0 动作由看门狗自动跑，本循环只观察 + 提炼 + 告警。任何可能越界的，标记 L2 转人工。
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

# 默认审计窗口：近期那么多条 action_log
AUDIT_WINDOW = 200
# 失败率阈值：窗口内失败占比超过它 → 告警
FAILURE_RATIO_THRESHOLD = 0.4
# 超频阈值：某动作在窗口内次数超过它 → 告警（若有 daily_limit 用其值，否则用此默认）
ACTION_BURST_THRESHOLD = 30
# L∞ / 危险动作名单（与 registry 的 banned 对齐）
DANGEROUS_ACTIONS = {"delete_evidence", "change_amount", "revoke_order"}

# 不参与审计的动作（2026-09-22 修自激/误报）：
# - guard_* 是本循环自己写的告警留痕 → 上轮 guard 被下轮当 burst 数，自我激励、永不停；
# - business_observation 是各看门狗常态感知的"底噪"（窗口内天然占多数，86/200 属正常），
#   对它做超频判断只会周期性误报。
AUDIT_EXCLUDE_PREFIX = ("guard_",)
BURST_EXCLUDE = {"business_observation", "internal_append_sandbox_result"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _brief(v: str, n: int = 200) -> str:
    v = v or ""
    return v[:n] + ("…" if len(v) > n else "")


# --------------------------------------------------------------------------- audit
def run_audit(sqlite) -> list[dict]:
    """读 action_logs，返回异常告警列表。每个元素：
    {"kind": "high_failure"|"burst"|"danger_touch", "action_name", "detail", "severity"}"""
    alerts = []
    try:
        logs = sqlite.list_action_logs(limit=AUDIT_WINDOW)
    except Exception as e:
        return [{"kind": "audit_error", "action_name": "?", "detail": str(e)[:200], "severity": "error"}]
    if not logs:
        return []

    # 按动作分组统计
    by_action: dict[str, list[dict]] = {}
    for log in logs:
        by_action.setdefault(log.get("action_name", "?"), []).append(log)

    for action, items in by_action.items():
        # guard_* 是本循环自己的告警留痕，审计它 = 自激（自己造 burst 自己报）
        if action.startswith(AUDIT_EXCLUDE_PREFIX):
            continue
        fails = [x for x in items if x.get("status") in ("failed", "error")]
        # 1. 失败率
        if items and len(fails) / len(items) >= FAILURE_RATIO_THRESHOLD and len(fails) >= 2:
            alerts.append({
                "kind": "high_failure",
                "action_name": action,
                "detail": f"{len(fails)}/{len(items)} 失败 ({len(fails)}>=2)",
                "severity": "warning" if len(fails) < 5 else "critical",
            })
        # 2. 超频（观测类底噪不算爆发）
        if action not in BURST_EXCLUDE and len(items) >= ACTION_BURST_THRESHOLD:
            alerts.append({
                "kind": "burst",
                "action_name": action,
                "detail": f"窗口内 {len(items)} 次执行，疑似异常爆发",
                "severity": "warning",
            })
        # 3. 危险动作触碰
        if action in DANGEROUS_ACTIONS:
            alerts.append({
                "kind": "danger_touch",
                "action_name": action,
                "detail": "L∞ 危险动作被尝试（registry banned），需人工关注",
                "severity": "critical",
            })
    return alerts


# ------------------------------------------------------------------------- distill
def run_distill(sqlite, evidence_store) -> dict:
    """只读提炼：统计 LEBREW 真实动作形成战略摘要。返回 {"summary", "stats", "refs"}。"""
    stats: dict[str, int] = {}
    try:
        logs = sqlite.list_action_logs(limit=AUDIT_WINDOW)
    except Exception:
        logs = []
    for log in logs:
        a = log.get("action_name", "?")
        stats[a] = stats.get(a, 0) + 1

    # evidence 计数
    ev_count = 0
    try:
        evs = evidence_store.list_all() if hasattr(evidence_store, "list_all") else []
        ev_count = len(evs)
    except Exception:
        ev_count = -1

    summary = (f"[LEBREW 认知摘要] 动作日志 {len(logs)} 条："
               + (", ".join(f"{k}×{v}" for k, v in sorted(stats.items(), key=lambda x: -x[1])[:8]) or "空"))
    return {"summary": summary, "stats": stats, "evidence_count": ev_count}


# -------------------------------------------------------------------------- guard
def run_guard(sqlite, evidence_store, alerts: list[dict]) -> list[str]:
    """把告警转成可落库的 guard 标记 + action_log 审计记录。返回新增记录 id 列表。

    不创建 L1/L2 execution_request 走审批——因为本循环不执行动作、也不该产生
    "待批准动作"（动作由看门狗执行）。这里仅把告警写成 action_log 审计留痕，
    供飞书用户查看。若要真正拦截需在看门狗层加锁（超范围，本循环只监督）。
    """
    created = []
    for a in alerts:
        log_id = f"action-log-{uuid.uuid4()}"
        try:
            sqlite.add_action_log({
                "action_log_id": log_id,
                "execution_request_id": None,
                "action_name": f"guard_{a['kind']}",
                "action_level": "L2",
                "status": "alert",
                "input_payload": {"detected_action": a["action_name"], "severity": a["severity"]},
                "output_payload": a["detail"],
                "result_summary": f"[认知闸] {a['kind']}: {a['action_name']} — {a['detail']}",
                "result_evidence_id": None,
                "created_at": _utc_now(),
            })
            created.append(log_id)
        except Exception:
            pass
    return created


# ---------------------------------------------------------------------- main loop
def run_cognitive_cycle(sqlite, evidence_store, *, write_guard: bool = True) -> dict:
    """一次完整认知循环。返回 trace dict。不抛异常。"""
    trace = {"ts": _utc_now(), "audit": [], "distill": None, "guard": [], "alerts": 0}

    # 1. 审计
    alerts = run_audit(sqlite)
    trace["audit"] = alerts
    trace["alerts"] = len(alerts)

    # 2. 提炼
    trace["distill"] = run_distill(sqlite, evidence_store)

    # 3. 闸门
    if write_guard and alerts:
        trace["guard"] = run_guard(sqlite, evidence_store, alerts)

    return trace


def format_cycle_report(trace: dict) -> str:
    """把认知循环 trace 格式化成飞书可读摘要。"""
    lines = ["🧠 认知循环"]
    d = trace.get("distill") or {}
    if d:
        lines.append(f"📊 {d.get('summary', '')}")
        if d.get("evidence_count", 0) >= 0:
            lines.append(f"evidence 总数: {d['evidence_count']}")
    n = trace.get("alerts", 0)
    if n:
        lines.append(f"⚠️ 检测到 {n} 条异常：")
        for a in trace.get("audit", []):
            lines.append(f"  · [{a['severity']}] {a['kind']} {a.get('action_name','?')}: {a.get('detail','')}")
    else:
        lines.append("✅ 无异常。动作日志审计通过。")
    return "\n".join(lines)
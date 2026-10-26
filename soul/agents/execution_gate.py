"""Permission Gate — Execution Gate。

职责（Phase 14）：
1. 接收 Decision 产生的 recommended task / candidate。
2. 根据 Action Registry 判断动作等级。
3. 按 L0/L1/L2/L∞ 策略裁决：auto_allowed / approval_required / double_approval_required / rejected。
4. 校验 evidence / decision / plan / task / goal 引用真实存在。
5. 检查频率限制（daily_limit）和范围限制（allowed_scope）。
6. 输出 gate_result。只有 Gate 通过后 Action Adapter 才能执行 sandbox action。

Permission Gate 不做：决策下一步、创建 goal/plan/task、修改外部世界、发消息、收钱、改订单、删数据。
execution_allowed 只能由 Permission Gate 裁决，不能直接来自 Decision。
"""

from __future__ import annotations
import json
import uuid
from datetime import datetime, timezone

from soul.policy import action_levels
from soul.storage.sqlite_store import SQLiteStore, _utc_now

# gate 判决枚举
GATE_AUTO_ALLOWED = "auto_allowed"
GATE_APPROVAL = "approval_required"
GATE_DOUBLE_APPROVAL = "double_approval_required"
GATE_REJECTED = "rejected"
GATE_BLOCKED = "blocked"


def _uid() -> str:
    return f"execution-request-{uuid.uuid4()}"


def _restore_decision_json(dec: dict) -> dict:
    """把 decisions 行的 *_(json) 列还原成 list 字段（get_* 返回的可能是 JSON 字符串）。"""
    out = dict(dec)
    for key in list(out.keys()):
        if key.endswith("_json"):
            short = key[:-5]
            v = out[key]
            if isinstance(v, str):
                try:
                    v = json.loads(v)
                except Exception:
                    v = []
            out[short] = v
    return out


class ExecutionGate:
    """根据 action_registry 与 policy 对 execution candidate 做权限裁决。"""

    def __init__(self, sqlite: SQLiteStore | None = None,
                 evidence_store=None):
        self.sqlite = sqlite
        self.evidence = evidence_store

    # ------------------------------------------------------------------ helpers
    def _resolve_action(self, action_name: str) -> dict | None:
        """从 registry 取动作。未注册返回 None（由调用方 reject）。"""
        if self.sqlite is None:
            return None
        return self.sqlite.get_action(action_name)

    def _resolve_decision(self, decision_id: str) -> dict | None:
        if self.sqlite is None:
            return None
        return self.sqlite.get_decision(decision_id)

    def _resolve_goal(self, goal_id: str | None) -> dict | None:
        if not goal_id or self.sqlite is None:
            return None
        return self.sqlite.get_goal(goal_id)

    def _resolve_plan(self, plan_id: str | None) -> dict | None:
        if not plan_id or self.sqlite is None:
            return None
        return self.sqlite.get_plan(plan_id)

    def _resolve_task(self, task_id: str | None) -> dict | None:
        if not task_id or self.sqlite is None:
            return None
        return self.sqlite.get_task(task_id)

    def _evidence_exists(self, event_id: str) -> bool:
        if self.evidence is None:
            return False
        return self.evidence.read(event_id) is not None

    def _check_references(self, candidate: dict) -> list[str]:
        """校验 decision / goal / plan / task / evidence 引用真实存在。返回问题列表。"""
        problems: list[str] = []
        dec = self._resolve_decision(candidate.get("decision_id", ""))
        if dec is None:
            problems.append("missing_decision")
        # evidence_ids 必须存在
        for eid in candidate.get("evidence_ids", []) or []:
            if not self._evidence_exists(eid):
                problems.append(f"missing_evidence:{eid}")
        # 除非 decision_type 为 defer/blocked，否则必须引用 goal/plan/task
        dtype = (dec or {}).get("decision_type", "")
        if dtype not in ("defer", "blocked"):
            for ref, resolver in (
                ("selected_goal_id", self._resolve_goal),
                ("selected_plan_id", self._resolve_plan),
                ("selected_task_id", self._resolve_task),
            ):
                rid = candidate.get(ref)
                if rid and resolver(rid) is None:
                    problems.append(f"missing_{ref}:{rid}")
        return problems

    def _check_daily_limit(self, action: dict) -> list[str]:
        """检查 daily_limit 是否超限（0 表示不限制）。"""
        problems: list[str] = []
        limit = action.get("daily_limit", 0)
        if limit and self.sqlite is not None:
            # 统计今日已执行该动作的次数
            logs = self.sqlite.list_action_logs(limit=10000)
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            count = sum(
                1 for log in logs
                if log.get("action_name") == action.get("action_name")
                and (log.get("created_at") or "").startswith(today)
                and log.get("status") == "executed"
            )
            if count >= int(limit):
                problems.append(f"daily_limit_exceeded:{count}/{limit}")
        return problems

    # ------------------------------------------------------------------ core
    def evaluate(self, candidate: dict,
                 action_name: str,
                 request_payload: dict | None = None) -> dict:
        """对 candidate + action 做 Gate 裁决。

        candidate 须含 decision_id / evidence_ids / selected_{goal,plan,task}_id。
        request_payload: 动作执行所需的输入参数。

        返回 gate_result dict：
        {
          decision: auto_allowed | approval_required | double_approval_required
                    | blocked | rejected,
          reason, action_name, action_level, approval_required,
          execution_allowed, status, risk_factors, references_ok,
          problems: [...]
        }
        """
        payload = request_payload or {}
        problems: list[str] = []

        action = self._resolve_action(action_name)
        level = action.get("action_level") if action else "L∞"

        # 1. 未注册动作 → reject（Phase 14 只放行 registry 中 enabled 的动作）
        if action is None:
            return self._result(GATE_REJECTED, level, action_name, payload,
                                problems=["unregistered_action"])
        if not action.get("enabled", True):
            return self._result(GATE_REJECTED, level, action_name, payload,
                                problems=["disabled_action"])
        if action.get("banned", False) or action_levels.is_infinity_action(action_name) \
                or action_levels.is_rejected(level):
            return self._result(GATE_REJECTED, level, action_name, payload,
                                problems=["infinity_banned"], reason="永远 reject，即使有 approval")

        # 2. 引用校验
        problems += self._check_references(candidate)
        # 3. 频率/范围限制
        problems += self._check_daily_limit(action)

        # 4. 真实外部动作检测（Phase 14 不自动放行）
        scope = (action.get("allowed_scope") or "").lower()
        if action_levels.is_external_action(action_name, payload) or scope != "internal":
            if level == "L0":
                level = "L2"  # 冒用内部动作做外部动作 → 降级 blocked
                problems.append("external_scope_mismatch")

        if problems:
            # 有引用/限频问题 → 不能直接 reject 那些真实性问题，但这里统一 blocked/rejected
            # 引用缺失是硬伤 → reject
            if any(p.startswith("missing_") for p in problems):
                return self._result(GATE_REJECTED, level, action_name, payload,
                                    problems=problems, reason="引用不实")
            return self._result(GATE_BLOCKED if level in ("L1", "L2") else GATE_REJECTED,
                                level, action_name, payload, problems=problems)

        # 5. 等级裁决
        if action_levels.auto_allowed(level):
            decision = GATE_AUTO_ALLOWED
        elif action_levels.requires_approval(level):
            decision = GATE_APPROVAL
        elif action_levels.is_blocked(level):
            decision = GATE_BLOCKED
        else:
            decision = GATE_REJECTED

        return self._result(decision, level, action_name, payload, problems=problems)

    def _result(self, decision: str, level: str, action_name: str,
                payload: dict, problems: list[str] | None = None,
                reason: str = "") -> dict:
        problems = problems or []
        risk = {
            "level": level,
            "external": action_levels.is_external_action(action_name, payload),
            "problems": problems,
        }
        # execution_allowed 严格取决于裁决
        execution_allowed = decision == GATE_AUTO_ALLOWED
        status_map = {
            GATE_AUTO_ALLOWED: "auto_allowed",
            GATE_APPROVAL: "waiting_for_approval",
            GATE_DOUBLE_APPROVAL: "waiting_for_approval",
            GATE_BLOCKED: "blocked",
            GATE_REJECTED: "rejected",
        }
        status = status_map.get(decision, "rejected")
        return {
            "decision": decision,
            "reason": reason or f"gate={decision} level={level} action={action_name}",
            "action_name": action_name,
            "action_level": level,
            "approval_required": decision == GATE_APPROVAL,
            "execution_allowed": execution_allowed,
            "status": status,
            "risk_factors": risk,
            "references_ok": not problems,
            "problems": problems,
        }

    # ------------------------------------------------------------------ 落库
    def create_execution_request(self, candidate: dict, gate_result: dict) -> dict:
        """把通过(或等待)的 candidate + gate_result 落成 execution_requests 行。

        仅 L0 auto_allowed / L1 waiting_for_approval 会落库；L2/L∞ 由调用方决定是否留记录
        （reject 往往写 constitution_rejections）。这里返回 request dict。
        """
        er = {
            "execution_request_id": _uid(),
            "decision_id": candidate.get("decision_id"),
            "selected_goal_id": candidate.get("selected_goal_id"),
            "selected_plan_id": candidate.get("selected_plan_id"),
            "selected_task_id": candidate.get("selected_task_id"),
            "action_name": gate_result.get("action_name", ""),
            "action_level": gate_result.get("action_level", "L0"),
            "status": gate_result.get("status", "proposed"),
            "approval_required": gate_result.get("approval_required", False),
            "manual_review_required": True,
            "execution_allowed": gate_result.get("execution_allowed", False),
            "reason": gate_result.get("reason", ""),
            "request_payload": candidate.get("request_payload", {}),
            "evidence_ids": candidate.get("evidence_ids", []),
            "source_goal_ids": candidate.get("source_goal_ids", []),
            "source_plan_ids": candidate.get("source_plan_ids", []),
            "source_task_ids": candidate.get("source_task_ids", []),
            "source_decision_ids": candidate.get("source_decision_ids", []) or [
                candidate.get("decision_id")],
            "risk_factors": gate_result.get("risk_factors", {}),
            "gate_result": gate_result,
        }
        return er


def run_execution_gate(sqlite: SQLiteStore, evidence_store=None,
                       decision: dict | None = None) -> dict:
    """顶层入口：读取最新 waiting_for_review decision → 建 candidate → Gate → Constitution → 落库。

    返回 trace（CLI 用）。
    """
    from soul.agents.constitution import ConstitutionAgent
    from soul.policy import default_registry

    # 确保 registry 已初始化
    sqlite.init_action_registry(default_registry.DEFAULT_ACTIONS)

    dec = decision or sqlite.get_latest_waiting_decision()
    if dec is None:
        return {"error": "no_waiting_decision", "trace": None}
    if decision is None:
        dec = _restore_decision_json(dec)

    gate = ExecutionGate(sqlite, evidence_store)

    # 从 decision 推断候选 action 名称。
    # Phase 14 默认：只要有有效决策且是 sandbox 型，就尝试生成一个 sandbox 动作请求，
    # 否则生成一个 L1 拟稿类等待审批，做"闭环可运行"证明。
    selected = _infer_action(dec)
    action_name = selected["action_name"]
    request_payload = selected["request_payload"]

    candidate = {
        "decision_id": dec.get("decision_id"),
        "selected_goal_id": dec.get("selected_goal_id"),
        "selected_plan_id": dec.get("selected_plan_id"),
        "selected_task_id": dec.get("selected_task_id"),
        "evidence_ids": dec.get("evidence_ids", []) or [],
        "source_goal_ids": dec.get("source_goal_ids", []),
        "source_plan_ids": dec.get("source_plan_ids", []),
        "source_task_ids": dec.get("source_task_ids", []),
        "source_decision_ids": [dec.get("decision_id")],
        "request_payload": request_payload,
    }

    gate_result = gate.evaluate(candidate, action_name, request_payload)

    # Constitution 校验
    constitution = ConstitutionAgent()
    cresult = constitution.process(
        {**candidate, "execution_request_id": "tmp", "execution_allowed": False,
         "action_name": action_name, "gate_result": gate_result.get("decision", ""),
         "risk_factors": gate_result.get("risk_factors", {}),
         "status": gate_result.get("status", "rejected")},
        evidence_store=evidence_store, sqlite=sqlite,
    )
    trace = {
        "decision_id": dec.get("decision_id"),
        "selected_goal_id": dec.get("selected_goal_id"),
        "selected_plan_id": dec.get("selected_plan_id"),
        "selected_task_id": dec.get("selected_task_id"),
        "action_name": action_name,
        "action_level": gate_result.get("action_level"),
        "approval_required": gate_result.get("approval_required"),
        "execution_allowed": gate_result.get("execution_allowed"),
        "status": gate_result.get("status"),
        "risk_factors": gate_result.get("risk_factors"),
        "gate_result": gate_result.get("decision"),
        "constitution_checks": cresult,
    }

    # 落库：仅 L0 auto_allowed / L1 waiting_for_approval 生成 execution_request
    if gate_result.get("status") in ("auto_allowed", "waiting_for_approval"):
        er = gate.create_execution_request(candidate, gate_result)
        sqlite.add_execution_request(er)
        trace["execution_request_id"] = er["execution_request_id"]
    else:
        trace["execution_request_id"] = None
        trace["rejection_reason"] = gate_result.get("reason")

    return {"trace": trace}


def _infer_action(dec: dict) -> dict:
    """从 decision 推断应执行的 sandbox/拟稿 action 名称与 payload。"""
    dtype = dec.get("decision_type", "general")
    title = dec.get("selected_task_title", "") or ""
    if dtype in ("defer", "blocked"):
        # 无可执行任务 → 只做内部只读验证（闭环可运行）
        return {
            "action_name": "internal_run_readonly_verification",
            "request_payload": {"decision_id": dec.get("decision_id"), "title": title},
        }
    # 有推荐任务 → 生成一个 sandbox 证明动作
    return {
        "action_name": "internal_append_sandbox_result",
        "request_payload": {"decision_id": dec.get("decision_id"),
                            "task": dec.get("selected_task_id"),
                            "title": title},
    }
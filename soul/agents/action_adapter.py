"""Action Adapter — Sandbox 动作执行器（Phase 14）。

只支持 sandbox/internal 动作，全部：
- 不修改 goal / plan / task / decision status。
- 不调外部 API、不发消息、不改真实文件。
- 返回 ActionResult。
- 写 action_log。
- 把执行结果追加为新的 action_result evidence（evidence.append），
  并把 result_evidence_id 指向新写入的 evidence event。

受支持动作（registry L0）：
- internal_record_review_note
- internal_create_checklist_snapshot
- internal_run_readonly_verification
- internal_append_sandbox_result
"""

from __future__ import annotations
import json
import uuid
from dataclasses import dataclass, field

from soul.storage.evidence_store import EvidenceStore


@dataclass
class ActionResult:
    """一次 sandbox action 的标准化结果。"""
    status: str  # success / failed
    result_summary: str
    output: dict = field(default_factory=dict)
    result_evidence_id: str | None = None
    action_log_id: str | None = None


class ActionAdapter:
    """沙箱动作执行器。构造时传入 sqlite + evidence_store。"""

    def __init__(self, sqlite=None, evidence_store: EvidenceStore | None = None):
        self.sqlite = sqlite
        self.evidence = evidence_store

    # ------------------------------------------------------------------ helpers
    def _append_evidence(self, summary: str, metadata: dict | None = None) -> dict | None:
        """把 action 结果追加为新 evidence event（不可变 hash chain）。"""
        if self.evidence is None:
            return None
        metadata = metadata or {}
        event = {
            "event_id": f"event-{uuid.uuid4()}",
            "event_type": "action_result",
            "source": "sandbox_action_adapter",
            "actor": "system",
            "content": "",
            "raw_content": summary,
            "metadata": metadata,
        }
        return self.evidence.compute_and_append(event)

    def _write_log(self, er: dict, result: ActionResult,
                   input_payload: dict) -> str | None:
        if self.sqlite is None:
            return None
        from soul.storage.sqlite_store import _utc_now
        log = {
            "action_log_id": f"action-log-{uuid.uuid4()}",
            "execution_request_id": er.get("execution_request_id"),
            "action_name": er.get("action_name", ""),
            "action_level": er.get("action_level", "L0"),
            "status": "executed" if result.status == "success" else "failed",
            "input_payload": input_payload,
            "output_payload": result.output,
            "result_summary": result.result_summary,
            "result_evidence_id": result.result_evidence_id,
            "created_at": _utc_now(),
        }
        return self.sqlite.add_action_log(log)

    # ------------------------------------------------------------------ dispatcher
    def run(self, er: dict, request_payload: dict | None = None) -> ActionResult:
        """执行 execution_request（已通过 Gate 且 status 允许运行时才调用）。"""
        action = er.get("action_name", "")
        payload = request_payload or er.get("request_payload", {}) or {}
        handler = {
            "internal_record_review_note": self._record_review_note,
            "internal_create_checklist_snapshot": self._create_checklist_snapshot,
            "internal_run_readonly_verification": self._run_readonly_verification,
            "internal_append_sandbox_result": self._append_sandbox_result,
        }.get(action)
        if handler is None:
            result = ActionResult(
                status="failed",
                result_summary=f"未注册或 Phase 14 不支持的动作: {action}",
                output={"error": "unknown_action"},
            )
        else:
            try:
                result = handler(er, payload)
            except Exception as e:  # pragma: no cover
                result = ActionResult(status="failed", result_summary=f"执行异常: {e}",
                                      output={"error": str(e)})
        # 写 action_log（无论成败）
        log_id = self._write_log(er, result, payload)
        result.action_log_id = log_id
        return result

    # ------------------------------------------------------------------ handlers
    def _record_review_note(self, er: dict, payload: dict) -> ActionResult:
        note = payload.get("note") or "review note"
        summary = f"为 decision {er.get('decision_id')} 写入 review note: {note}"
        ev = self._append_evidence(summary, {"action": "internal_record_review_note",
                                             "decision_id": er.get("decision_id")})
        return ActionResult(status="success", result_summary=summary,
                            output={"note": note},
                            result_evidence_id=ev.get("event_id") if ev else None)

    def _create_checklist_snapshot(self, er: dict, payload: dict) -> ActionResult:
        snapshot = payload.get("snapshot") or {"items": [], "task": er.get("selected_task_id")}
        summary = f"为 task {er.get('selected_task_id')} 生成 checklist snapshot"
        ev = self._append_evidence(summary, {"action": "internal_create_checklist_snapshot",
                                             "task_id": er.get("selected_task_id")})
        return ActionResult(status="success", result_summary=summary,
                            output={"snapshot": snapshot},
                            result_evidence_id=ev.get("event_id") if ev else None)

    def _run_readonly_verification(self, er: dict, payload: dict) -> ActionResult:
        # 只读验证：不改数据，仅汇总
        verdict = "readonly_ok"
        summary = f"只读验证完成: {verdict}（decision {er.get('decision_id')}）"
        ev = self._append_evidence(summary, {"action": "internal_run_readonly_verification",
                                             "decision_id": er.get("decision_id")})
        return ActionResult(status="success", result_summary=summary,
                            output={"verification": verdict, "readonly": True},
                            result_evidence_id=ev.get("event_id") if ev else None)

    def _append_sandbox_result(self, er: dict, payload: dict) -> ActionResult:
        summary = f"sandbox result: action adapter 闭环可运行（request {er.get('execution_request_id')}）"
        ev = self._append_evidence(summary, {"action": "internal_append_sandbox_result",
                                             "execution_request_id": er.get("execution_request_id")})
        return ActionResult(status="success", result_summary=summary,
                            output={"sandbox": True,
                                    "execution_request_id": er.get("execution_request_id")},
                            result_evidence_id=ev.get("event_id") if ev else None)


def run_approved_action(sqlite, evidence_store, execution_request: dict,
                        request_payload: dict | None = None) -> dict:
    """顶层入口：执行已批准 / auto_allowed 的 execution_request。

    规则：
    - L0 auto_allowed 可运行
    - L1 approved 可运行
    - L1 未 approved 不可运行
    - L2 blocked / L∞ rejected 不可运行
    - 执行 sandbox adapter；写 action_log；追加 action_result evidence；
      不修改 goal/plan/task/decision status。
    """
    if execution_request is None:
        return {"error": "no_execution_request"}
    status = execution_request.get("status", "")
    level = execution_request.get("action_level", "")
    allowed = False
    if status == "auto_allowed" and level == "L0":
        allowed = True
    elif status == "approved":  # L1 已审批
        allowed = True
    if not allowed:
        return {"error": f"execution_request 不可执行（status={status} level={level}）",
                "reason": "not_run"}
    adapter = ActionAdapter(sqlite, evidence_store)
    result = adapter.run(execution_request, request_payload)
    # 更新 execution_request status → executed
    if sqlite is not None and result.status == "success":
        sqlite.update_execution_request(execution_request.get("execution_request_id"),
                                        status="executed")
    elif sqlite is not None:
        sqlite.update_execution_request(execution_request.get("execution_request_id"),
                                        status="failed")
    return {"status": result.status, "result_summary": result.result_summary,
            "result_evidence_id": result.result_evidence_id,
            "action_log_id": result.action_log_id}
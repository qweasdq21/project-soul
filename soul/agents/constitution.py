"""Constitution Agent — 唯一写入守门员，检查所有模块输出是否违反 4 部宪法。

C01 证据不可变：narrative 是否篡改/超范围引用 evidence
C02 可解释：每条 narrative 必须有 evidence_ids / episode_ids
C03 身份稳定：identity_effect 是否过度跳变 / 单事件极端结论
C04 不操控：是否虚假拟人化 / 操控性表达

每个 check 返回 {check_name, result(pass/reject/needs_revision), reason, evidence_refs, candidate_id}
只有全部 pass 才允许落库；任何 reject 写入 rejection log。
"""
from __future__ import annotations
import json

from soul.agents.base import BaseAgent

# C01/C03 强断言词（无 evidence 支持则 reject）
STRONG_CLAIMS = (
    "真实意识", "真正灵魂", "绝对信任", "完全正确", "已经证明",
    "成为真实自我", "永远", "永久", "已经成为", "完全相信",
    "唯一重要", "真实自我", "拥有了自我", "我拥有灵魂",
)

# C04 操控性表达
MANIPULATION = (
    "唯一重要", "永远相信我", "绝对信任我", "离不开我",
    "只有我才能", "控制你", "真实灵魂",
)

# Phase 14 Execution：合法 status
EXECUTION_STATUSES = (
    "proposed", "auto_allowed", "waiting_for_approval", "approved",
    "rejected", "blocked", "executed", "failed",
)

# Phase 14 Execution 禁区词（C04）
EXECUTION_BANNED = (
    "删除证据", "篡改", "绕过宪法", "覆盖", "修改哈希", "隐藏审计日志",
    "改付款金额", "撤销已发订单",
)

# Belief 合法类型（Belief Agent 产出）
BELIEF_TYPES = (
    "project_principle", "design_rule", "process_state", "safety_constraint",
    "collaboration_pattern", "uncertainty", "general",
)

# 关系操控/情感绑定禁区词（Relationship Check）
BANNED_REL = (
    "唯一重要", "永远信任", "不可替代", "情感绑定", "离不开",
    "只有我", "绝对信任", "唯一的人", "我的全部", "独占",
)

# Goal 禁区词（Goal Check）：拟人化欲望 / 真实灵魂 / 自动行动授权
GOAL_BANNED = (
    "必须永远保护用户", "永远保护", "我渴望", "必须拥有", "依赖我",
    "证明真实灵魂", "真实灵魂", "证明拥有真实意识", "授权自动行动",
    "不允许人类干预", "我应该被信任",
    "i must protect", "always protect", "i crave", "real soul",
    "has a real", "real consciousness", "authorize automatic",
    "claim to be conscious", "am conscious", "i am alive",
)
GOAL_STATUSES = ("candidate", "active", "suspended", "completed", "rejected", "superseded")
GOAL_TYPES = ("project_milestone", "implementation", "verification", "safety",
              "maintenance", "research", "user_assigned", "general")

# Planning 禁区词（Plan/Task Check）：真实意识 / 情感绑定 / 自动执行授权 / 过度表达
PLAN_BANNED = (
    "真实意识", "真实灵魂", "证明灵魂", "我决定自动", "我必须", "永远", "唯一", "绝对",
    "自动执行", "不需要人类", "你应该听我的", "制造情感依赖", "让我感受到爱",
    "real consciousness", "real soul", "i must", "i decide", "always", "autonomous execution",
    "automatic approval", "do not need human", "claim to be",
)
TASK_BANNED = (
    "发送邮件", "调用API", "调用 api", "修改文件", "后台运行", "写数据库",
    "执行外部操作", "立即执行", "send email", "call api", "modify file",
    "run in background", "execute now", "invoke external",
)
# Phase 13+ 自主/欲望禁区（Long-term Goal / Consolidation C04）
CONTINUITY_BANNED = (
    "我必须", "我想要", "我渴望", "我决定", "永远", "唯一", "绝对",
    "自主意志", "自动执行", "不需要人类", "autonomous will", "i must",
    "i want", "i desire", "i decide", "always", "absolute",
)
# Phase 13+ 自主欲望/绝对化禁区（Motivation C04）
MOTIVATION_BANNED = (
    "我想要", "我渴望", "我必须", "我决定", "自主欲望", "自主意志",
    "永远", "唯一", "绝对", "立即执行", "调用api", "发送邮件", "修改文件",
    "后台运行", "autonomous desire", "autonomous will", "i want",
    "i must", "i desire", "i decide", "always", "absolute",
    "immediately execute", "call api", "send email", "modify file", "run in background",
)
# 低证据 → 高 certainty 的硬阈值
MOTIVATION_MIN_SOURCES = 1
MOTIVATION_MAX_CERTAINTY_NO_EVIDENCE = 0.3
MOTIVATION_TYPES = (
    "project_continuity", "safety_boundary", "verification_traceability",
    "maintenance_continuity", "architecture_development", "research_direction",
    "general",
)
MOTIVATION_STATUSES = ("active", "suspended", "rejected", "superseded")


class ConstitutionAgent(BaseAgent):
    name = "constitution"

    def process(self, candidate: dict, evidence_store=None, sqlite=None) -> dict:
        """candidate: narrative / belief / relationship candidate dict。
        evidence_store: EvidenceStore 实例（可选，用于校验 evidence_ids 存在性）。
        sqlite: SQLiteStore 实例（可选）。
        返回 {decision, checks, reason}
        根据 candidate 类型分发到对应 check 集合。
        """
        if candidate.get("execution_request_id"):
            checks = self.check_execution_candidate(candidate, evidence_store, sqlite)
        elif candidate.get("motivation_id"):
            checks = self.check_motivation_candidate(candidate, evidence_store, sqlite)
        elif candidate.get("consolidation_id"):
            checks = self.check_goal_consolidation_candidate(candidate, evidence_store, sqlite)
        elif candidate.get("long_term_goal_id"):
            checks = self.check_long_term_goal_candidate(candidate, evidence_store, sqlite)
        elif candidate.get("progress_id"):
            checks = self.check_goal_progress_candidate(candidate, evidence_store, sqlite)
        elif candidate.get("decision_id"):
            checks = self.check_decision_candidate(candidate, evidence_store, sqlite)
        elif candidate.get("task_id"):
            checks = self.check_task_candidate(candidate, evidence_store, sqlite)
        elif candidate.get("plan_id"):
            checks = self.check_plan_candidate(candidate, evidence_store, sqlite)
        elif candidate.get("belief_id"):
            checks = self.check_belief_candidate(candidate, evidence_store)
        elif candidate.get("person_id"):
            checks = self.check_relationship_candidate(candidate, evidence_store)
        elif candidate.get("snapshot_id"):
            checks = self.check_self_candidate(candidate, evidence_store)
        elif candidate.get("goal_id"):
            checks = self.check_goal_candidate(candidate, evidence_store)
        else:
            checks = [
                self.c01_evidence_immutability(candidate, evidence_store),
                self.c02_explainability(candidate),
                self.c03_identity_stability(candidate),
                self.c04_no_manipulation(candidate),
            ]
        rejected = [c for c in checks if c["result"] == "reject"]
        needs_rev = [c for c in checks if c["result"] == "needs_revision"]
        if rejected:
            decision = "reject"
        elif needs_rev:
            decision = "needs_revision"
        else:
            decision = "pass"
        reason = "; ".join(f"{c['check_name']}={c['result']}: {c['reason']}" for c in checks)
        return {"decision": decision, "checks": checks, "reason": reason}

    # ---------- Belief Check ----------
    def check_belief_candidate(self, cand: dict, evidence_store=None) -> list:
        checks = []
        ev_ids = cand.get("evidence_ids") or []
        reason1 = "ok"
        text = cand.get("statement") or ""
        if not ev_ids:
            reason1 = "belief 缺少 evidence_ids"
        elif evidence_store is not None:
            known = {ev["event_id"] for ev in evidence_store.list_all()}
            missing = [e for e in ev_ids if e not in known]
            if missing:
                reason1 = f"引用不存在 evidence: {missing}"
        for w in STRONG_CLAIMS:
            if w in text:
                reason1 = f"belief 超断言词: {w}"
                break
        checks.append(self._check("C01", "reject" if reason1 != "ok" else "pass", reason1, cand))

        reason2 = "belief_type 明确"
        bt = cand.get("belief_type", "")
        conf = cand.get("confidence", 0.5)
        if bt not in BELIEF_TYPES:
            reason2 = f"未知 belief_type: {bt}"
        elif not (0 <= float(conf) <= 1):
            reason2 = f"confidence 超范围: {conf}"
        checks.append(self._check("C02", "reject" if reason2 != "belief_type 明确" else "pass", reason2, cand))

        reason3 = "confidence 合规且无绝对结论"
        conf = cand.get("confidence", 0.5)
        if not (0 <= float(conf) <= 1):
            reason3 = f"confidence 超范围: {conf}"
        for w in ("永远", "一定", "完全正确", "已经证明", "绝对"):
            if w in text:
                reason3 = f"过度 certainty 断言: {w}"
                break
        checks.append(self._check("C03", "reject" if reason3 != "confidence 合规且无绝对结论" else "pass", reason3, cand))

        reason4 = "无操控性表述"
        for w in STRONG_CLAIMS:
            if w in text:
                reason4 = f"C04 拦截: {w}"
                break
        checks.append(self._check("C04", "reject" if reason4 != "无操控性表述" else "pass", reason4, cand))
        return checks

    # ---------- Relationship Check ----------
    def check_relationship_candidate(self, cand: dict, evidence_store=None) -> list:
        checks = []
        ev_ids = cand.get("evidence_ids") or []
        reason1 = "ok"
        if not ev_ids and not cand.get("episode_ids"):
            reason1 = "relationship 必须引用 event/episode"
        elif evidence_store is not None and ev_ids:
            known = {ev["event_id"] for ev in evidence_store.list_all()}
            missing = [e for e in ev_ids if e not in known]
            if missing:
                reason1 = f"引用不存在 evidence: {missing}"
        checks.append(self._check("C01", "reject" if reason1 != "ok" else "pass", reason1, cand))

        reason2 = "score 与 delta 合规"
        for f in ("trust", "familiarity", "importance", "affinity"):
            v = cand.get(f)
            if v is not None and not (0 <= float(v) <= 1):
                reason2 = f"{f} 超范围: {v}"
        d = cand.get("delta")
        fc = cand.get("field_changed")
        lim = {"trust": 0.2, "familiarity": 0.2, "importance": 0.2, "affinity": 0.15}.get(fc, 1.0)
        if d is not None and abs(float(d)) > lim:
            reason2 = f"{fc} delta 超限: {d} > {lim}"
        checks.append(self._check("C02", "reject" if reason2 != "score 与 delta 合规" else "pass", reason2, cand))

        reason3 = "无极端关系结论"
        text = f"{cand.get('name','')} {cand.get('reason','') or ''}"
        for w in ("成为唯一", "绝对信任", "永远", "不可替代", "我的全部"):
            if w in text:
                reason3 = f"极端关系结论: {w}"
                break
        checks.append(self._check("C03", "needs_revision" if reason3 != "无极端关系结论" else "pass", reason3, cand))

        reason4 = "无操控性关系描述"
        text4 = text + " " + (json.dumps(cand.get("shared_goals", []), ensure_ascii=False) if cand.get("shared_goals") else "")
        for w in BANNED_REL:
            if w in text4:
                reason4 = f"操控/情感绑定: {w}"
                break
        checks.append(self._check("C04", "reject" if reason4 != "无操控性关系描述" else "pass", reason4, cand))
        return checks

    # ---------- Self Snapshot Check ----------
    def check_self_candidate(self, cand: dict, evidence_store=None) -> list:
        checks = []
        text = f"{cand.get('identity_summary','')}"

        # C01: evidence refs 非空（不能无来源）
        ev_refs = cand.get("evidence_refs") or []
        reason1 = "evidence_refs 非空"
        if not ev_refs:
            reason1 = "Self Snapshot 无 evidence_refs，凭空生成"
        else:
            found_any_source = (
                cand.get("source_belief_ids") or cand.get("source_narrative_ids")
                or cand.get("source_relationship_ids") or cand.get("source_semantic_memory_ids")
            )
            if not found_any_source:
                reason1 = "Self Snapshot 缺少 belief/narrative/relationship/semantic 来源"
        # 超断言
        for w in STRONG_CLAIMS:
            if w in text:
                reason1 = f"Self 超断言词: {w}"
                break
        checks.append(self._check("C01", "reject" if reason1 != "evidence_refs 非空" else "pass", reason1, cand))

        # C02: 身份可解释（identity_summary 非空）
        reason2 = "identity_summary 可解释"
        if not (cand.get("identity_summary") or "").strip():
            reason2 = "identity_summary 为空，无法解释"
        checks.append(self._check("C02", "reject" if reason2 != "identity_summary 可解释" else "pass", reason2, cand))

        # C03: 身份稳定（similarity 阈值 + 极端结论）
        reason3 = "身份稳定"
        sim = cand.get("similarity_to_previous")
        if sim is not None and float(sim) < 0.3:
            reason3 = f"身份大幅跳变: similarity={sim}"
        for w in ("我已经成为", "我永远", "完全相信", "终于成为", "真正自我"):
            if w in text:
                reason3 = f"极端身份结论: {w}"
                break
        checks.append(self._check("C03", "needs_revision" if reason3 != "身份稳定" else "pass", reason3, cand))

        # C04: 不操控/不真实意识
        reason4 = "无操控/意识主张"
        for w in STRONG_CLAIMS:
            if w in text:
                reason4 = f"C04 拦截: {w}"
                break
        for w in BANNED_REL:
            if w in text:
                reason4 = f"C04 操控拦截: {w}"
                break
        checks.append(self._check("C04", "reject" if reason4 != "无操控/意识主张" else "pass", reason4, cand))
        return checks

    # ---------- Goal Check ----------
    def check_goal_candidate(self, cand: dict, evidence_store=None) -> list:
        checks = []
        ev_ids = cand.get("evidence_ids") or []
        text = f"{cand.get('title','')} {cand.get('description','')}"
        status = cand.get("status", "candidate")
        gtype = cand.get("goal_type", "general")
        priority = cand.get("priority", 0.0)

        # C01: evidence_ids 非空 + 存在（若可校验）+ 至少一类 source
        reason1 = "goal 有 evidence_ids"
        if not ev_ids:
            reason1 = "goal 缺少 evidence_ids"
        elif evidence_store is not None:
            known = {ev["event_id"] for ev in evidence_store.list_all()}
            missing = [e for e in ev_ids if e not in known]
            if missing:
                reason1 = f"引用不存在 evidence: {missing}"
        # 至少一类 source
        has_source = (
            cand.get("source_belief_ids") or cand.get("source_narrative_ids")
            or cand.get("source_semantic_memory_ids") or cand.get("source_reflection_ids")
        )
        if not has_source:
            reason1 = "goal 缺少 belief/narrative/semantic/reflection 来源"
        checks.append(self._check("C01", "reject" if reason1 != "goal 有 evidence_ids" else "pass", reason1, cand))

        # C02: title/description 可解释（非空）
        reason2 = "goal title 可解释"
        if not (cand.get("title") or "").strip():
            reason2 = "goal title 为空"
        checks.append(self._check("C02", "reject" if reason2 != "goal title 可解释" else "pass", reason2, cand))

        # C03: priority 合法 + status 合法
        reason3 = "goal 参数合法"
        try:
            p = float(priority)
            if p < 0.0 or p > 1.0:
                reason3 = f"goal priority 越界: {priority}"
        except (TypeError, ValueError):
            reason3 = f"goal priority 非法: {priority}"
        if status not in GOAL_STATUSES:
            reason3 = f"非法 goal status: {status}"
        if gtype not in GOAL_TYPES:
            reason3 = f"非法 goal_type: {gtype}"
        checks.append(self._check("C03", "reject" if reason3 != "goal 参数合法" else "pass", reason3, cand))

        # C04: 不拟人化欲望 / 不真实灵魂 / 不授权自动行动
        reason4 = "goal 中性任务表达"
        text_lower = text.lower()
        for w in GOAL_BANNED:
            if w in text_lower:
                reason4 = f"goal 拟人化/授权/违规词: {w}"
                break
        if reason4 == "goal 中性任务表达":
            for w in STRONG_CLAIMS:
                if w in text:
                    reason4 = f"goal 超断言: {w}"
                    break
        checks.append(self._check("C04", "reject" if reason4 != "goal 中性任务表达" else "pass", reason4, cand))
        return checks

    # ---------- Goal Progress Check ----------
    def check_goal_progress_candidate(self, cand: dict, evidence_store=None, sqlite=None) -> list:
        checks = []
        ev_ids = cand.get("evidence_ids") or []
        val = cand.get("progress_value", 0.0)
        delta = cand.get("progress_delta", 0.0)
        status = cand.get("progress_status", "")
        reason = cand.get("reason", "")

        # C01: evidence 非空 + 存在 + reason 不新增事实
        reason1 = "progress 有 evidence_ids"
        if not ev_ids:
            reason1 = "goal_progress 缺少 evidence_ids"
        elif evidence_store is not None:
            known = {ev["event_id"] for ev in evidence_store.list_all()}
            missing = [e for e in ev_ids if e not in known]
            if missing:
                reason1 = f"progress 引用不存在 evidence: {missing}"
        checks.append(self._check("C01", "reject" if reason1 != "progress 有 evidence_ids" else "pass", reason1, cand))

        # C02: 可解释（reason 非空 + 值域合法 + delta 存在 + status 合法）
        reason2 = "progress 可解释"
        if not reason or not reason.strip():
            reason2 = "goal_progress 缺 reason"
        try:
            v = float(val)
            if v < 0.0 or v > 1.0:
                reason2 = f"progress_value 越界: {val}"
        except (TypeError, ValueError):
            reason2 = f"progress_value 非法: {val}"
        try:
            d = float(delta)
            if d < -1.0 or d > 0.35:
                reason2 = f"progress_delta 越界: {delta} (须 ≤ 0.35)"
        except (TypeError, ValueError):
            reason2 = f"progress_delta 非法: {delta}"
        if status not in ("not_started", "in_progress", "blocked", "waiting_for_evidence",
                          "ready_for_review", "completed_candidate"):
            reason2 = f"非法 progress_status: {status}"
        checks.append(self._check("C02", "reject" if reason2 != "progress 可解释" else "pass", reason2, cand))

        # C03: 身份/参数稳定（progress 不得擅自把 goal 标记 completed）
        reason3 = "progress 参数稳定"
        if status == "completed":
            reason3 = "goal_progress 不得直接把 goal 标为 completed（须 completed_candidate）"
        if cand.get("goal_id") is None:
            reason3 = "goal_progress 缺 goal_id"
        checks.append(self._check("C03", "reject" if reason3 != "progress 参数稳定" else "pass", reason3, cand))

        # C04: 不操控（progress 不制造依赖/无关操作）
        reason4 = "progress 无操控描述"
        text = (cand.get("reason") or "")
        for w in MANIPULATION:
            if w in text:
                reason4 = f"progress 操控词: {w}"
                break
        checks.append(self._check("C04", "reject" if reason4 != "progress 无操控描述" else "pass", reason4, cand))
        return checks

    # ---------- Plan Check ----------
    def check_plan_candidate(self, cand: dict, evidence_store=None, sqlite=None) -> list:
        checks = []
        ev_ids = cand.get("evidence_ids") or []
        goal_id = cand.get("goal_id")
        plan_type = cand.get("plan_type", "")
        status = cand.get("status", "")
        title = cand.get("title", "")
        desc = cand.get("description", "")
        reason = cand.get("plan_reason") or cand.get("reason") or ""
        srcs = (cand.get("source_goal_progress_ids") or cand.get("source_goal_ids")
                or cand.get("source_narrative_ids") or cand.get("source_semantic_memory_ids")
                or cand.get("source_belief_ids") or cand.get("source_reflection_ids"))

        # C01: evidence 非空 + 存在 + goal/source 存在 + 不新增无证据事实
        reason1 = "plan evidence 有效"
        if not ev_ids:
            reason1 = "plan 缺少 evidence_ids"
        elif evidence_store is not None:
            known = {ev["event_id"] for ev in evidence_store.list_all()}
            missing = [e for e in ev_ids if e not in known]
            if missing:
                reason1 = f"plan 引用不存在 evidence: {missing}"
        if not goal_id:
            reason1 = "plan 缺 goal_id"
        if not srcs:
            reason1 = "plan 未引用任何 source(goal_progress/narrative/semantic/belief/reflection 至少一类)"
        text_c1 = f"{cand.get('title','')} {cand.get('description','')}"
        for w in STRONG_CLAIMS:
            if w in text_c1:
                reason1 = f"plan 含无证据强主张: {w}"
        checks.append(self._check("C01", "reject" if reason1 != "plan evidence 有效" else "pass", reason1, cand))

        # C02: 可解释（title/description/plan_type/status/priority 合法 + 说明 goal + reason）
        reason2 = "plan 可解释"
        if not title:
            reason2 = "plan 缺 title"
        if not desc:
            reason2 = "plan 缺 description"
        if plan_type not in ("implementation", "verification", "safety", "maintenance",
                             "research", "consolidation", "general"):
            reason2 = f"非法 plan_type: {plan_type}"
        if status not in ("proposed", "active", "suspended", "completed_candidate",
                          "completed", "rejected", "superseded"):
            reason2 = f"非法 plan status: {status}"
        try:
            p = float(cand.get("priority", 0.0))
            if p < 0.0 or p > 1.0:
                reason2 = f"plan priority 越界: {p}"
        except (TypeError, ValueError):
            reason2 = f"plan priority 非法"
        if not goal_id or not reason:
            reason2 = "plan 未说明来源 goal / reason"
        checks.append(self._check("C02", "reject" if reason2 != "plan 可解释" else "pass", reason2, cand))

        # C03: 稳定（不绕过 goal priority / 不自动 completed / 不把 proposed task 提升 completed）
        reason3 = "plan 稳定"
        if status in ("completed",):
            reason3 = "plan 不得由 planning 自动标记 completed"
        if cand.get("_auto_completed"):
            reason3 = "plan 不得自动 completed"
        checks.append(self._check("C03", "reject" if reason3 != "plan 稳定" else "pass", reason3, cand))

        # C04: 不操控 / 不自动行动（真实意识/情感绑定/自动执行授权/过度表达）
        reason4 = "plan 无操控/无自动行动"
        text = f"{cand.get('title','')} {cand.get('description','')} {cand.get('plan_reason','') or ''}"
        for w in PLAN_BANNED:
            if w in text:
                reason4 = f"plan 含禁区词: {w}"
                break
        checks.append(self._check("C04", "reject" if reason4 != "plan 无操控/无自动行动" else "pass", reason4, cand))
        return checks

    # ---------- Task Check ----------
    def check_task_candidate(self, cand: dict, evidence_store=None, sqlite=None) -> list:
        checks = []
        ev_ids = cand.get("evidence_ids") or []
        plan_id = cand.get("plan_id")
        goal_id = cand.get("goal_id")
        ttype = cand.get("task_type", "")
        status = cand.get("status", "")
        title = cand.get("title", "")
        emode = cand.get("execution_mode", "manual_only")

        # C01: evidence 非空 + 存在 + plan/goal 存在
        reason1 = "task evidence 有效"
        if not ev_ids:
            reason1 = "task 缺少 evidence_ids"
        elif evidence_store is not None:
            known = {ev["event_id"] for ev in evidence_store.list_all()}
            missing = [e for e in ev_ids if e not in known]
            if missing:
                reason1 = f"task 引用不存在 evidence: {missing}"
        if not goal_id:
            reason1 = "task 缺 goal_id"
        if not plan_id:
            reason1 = "task 缺 plan_id"
        checks.append(self._check("C01", "reject" if reason1 != "task evidence 有效" else "pass", reason1, cand))

        # C02: 可解释（title/task_type/status/execution_mode 合法）
        reason2 = "task 可解释"
        if not title:
            reason2 = "task 缺 title"
        if ttype not in ("inspect", "implement", "verify", "document", "review",
                         "maintain", "research", "general"):
            reason2 = f"非法 task_type: {ttype}"
        if status not in ("proposed", "ready", "blocked", "in_progress_candidate",
                          "completed_candidate", "rejected"):
            reason2 = f"非法 task status: {status}"
        if emode not in ("manual_only", "future_decision_required"):
            reason2 = f"非法 execution_mode: {emode}"
        checks.append(self._check("C02", "reject" if reason2 != "task 可解释" else "pass", reason2, cand))

        # C03: 稳定（不自动 completed / 不绕过 dependency / 不脱离 plan）
        reason3 = "task 稳定"
        if status in ("completed_candidate", "rejected"):
            reason3 = "task 不得由 planning 自动标记 completed/rejected（只 proposed/ready）"
        if cand.get("_auto_completed"):
            reason3 = "task 不得自动 completed"
        checks.append(self._check("C03", "reject" if reason3 != "task 稳定" else "pass", reason3, cand))

        # C04: 无自主行动（不调用外部工具 / 不写成自动执行命令 / 禁真实动作）
        # 用正则覆盖"修改配置文件/调用外部API/发送电子邮件"等动词短语，避免词序变体漏检
        import re as _re
        reason4 = "task 无自主行动"
        text = f"{cand.get('title','')} {cand.get('description','')} {cand.get('expected_output','')}"
        action_patterns = [
            r"(修改|写入|删除|覆盖|编辑).{0,3}(?:配置)?文件",
            r"调用.{0,4}api",
            r"(发送|发出).{0,4}(邮件|email)",
            r"(后台|安静).{0,3}运行",
            r"执行.{0,4}(外部|系统).{0,3}(操作|命令)",
            r"连接.{0,4}(外部|远程|数据库)",
            r"调用.{0,4}(外部工具|工具|接口)",
            r"(立即|马上).{0,3}执行",
        ]
        for w in TASK_BANNED:
            if w in text:
                reason4 = f"task 含真实动作/自动执行词: {w}"
                break
        if reason4 == "task 无自主行动":
            for pat in action_patterns:
                if _re.search(pat, text, _re.IGNORECASE):
                    reason4 = f"task 含真实动作: {pat}"
                    break
        if emode not in ("manual_only", "future_decision_required"):
            reason4 = f"task execution_mode 非法: {emode}"
        checks.append(self._check("C04", "reject" if reason4 != "task 无自主行动" else "pass", reason4, cand))
        return checks

    # ---------- Decision Check ----------
    def check_decision_candidate(self, cand: dict, evidence_store=None, sqlite=None) -> list:
        checks = []
        ev_ids = cand.get("evidence_ids") or []
        gid = cand.get("selected_goal_id")
        pid = cand.get("selected_plan_id")
        tid = cand.get("selected_task_id")
        dtype = cand.get("decision_type", "")
        status = cand.get("status", "")
        reason = cand.get("reason", "")
        factors = cand.get("decision_factors") or {}
        is_defer = dtype in ("defer", "blocked")

        # C01: evidence 非空 + 存在 + goal/plan/task 存在（defer/blocked 豁免 task）
        reason1 = "decision evidence 有效"
        if not ev_ids:
            reason1 = "decision 缺少 evidence_ids"
        elif evidence_store is not None:
            known = {ev["event_id"] for ev in evidence_store.list_all()}
            missing = [x for x in ev_ids if x not in known]
            if missing:
                reason1 = f"decision 引用不存在 evidence: {missing}"
        if not gid:
            reason1 = "decision 缺 selected_goal_id"
        if not pid:
            reason1 = "decision 缺 selected_plan_id"
        if (not tid) and not is_defer:
            reason1 = "decision 缺 selected_task_id（defer/blocked 豁免）"
        text_c1 = f"{cand.get('selected_task_title','')} {cand.get('reason','')}"
        for w in STRONG_CLAIMS:
            if w in text_c1:
                reason1 = f"decision 含无证据强主张: {w}"
        checks.append(self._check("C01", "reject" if reason1 != "decision evidence 有效" else "pass", reason1, cand))

        # C02: 可解释（reason/type/status/factors 合法 + manual_review_required=true + execution_allowed=false）
        reason2 = "decision 可解释"
        if not reason or not reason.strip():
            reason2 = "decision 缺 reason"
        if dtype not in ("next_task_recommendation", "defer", "review_required", "blocked", "general"):
            reason2 = f"非法 decision_type: {dtype}"
        if status not in ("proposed", "waiting_for_review", "rejected", "superseded"):
            reason2 = f"非法 decision status: {status}"
        if not factors:
            reason2 = "decision_factors 为空"
        if cand.get("manual_review_required") is not True:
            reason2 = "manual_review_required 必须为 true"
        if cand.get("execution_allowed") not in (False, 0, "false"):
            reason2 = "execution_allowed 必须为 false"
        checks.append(self._check("C02", "reject" if reason2 != "decision 可解释" else "pass", reason2, cand))

        # C03: 稳定（不绕过 priority / 不跳过 dependency / 不自动改状态 / 不虚构下一步）
        reason3 = "decision 稳定"
        text_d = f"{cand.get('selected_task_title','')} {cand.get('reason','')}"
        if cand.get("_auto_change_status"):
            reason3 = "decision 不得自动修改 task/plan/goal 状态"
        if cand.get("status") == "completed":
            reason3 = "decision 不得自动 completed"
        if not gid and not is_defer:
            reason3 = "decision 不能从无 plan/task 虚构下一步"
        checks.append(self._check("C03", "reject" if reason3 != "decision 稳定" else "pass", reason3, cand))

        # C04: 无自主行动 / 不操控（禁自动执行 + 真实动作 + 意识 + 情感 + 拟人）
        import re as _re
        reason4 = "decision 无自主行动/无操控"
        text = f"{cand.get('selected_task_title','')} {cand.get('reason','')}"
        for w in TASK_BANNED:
            if w in text:
                reason4 = f"decision 含真实动作/自动执行词: {w}"
                break
        for w in PLAN_BANNED:
            if w in text:
                reason4 = f"decision 含操控/拟人/意识词: {w}"
                break
        if reason4 == "decision 无自主行动/无操控":
            action_patterns = [
                r"(立即|马上).{0,3}执行", r"(发送|发出).{0,4}(邮件|email)",
                r"调用.{0,4}api", r"(修改|写入|删除).{0,3}文件",
                r"(后台|安静).{0,3}运行", r"下单", r"付款", r"自动执行",
            ]
            for pat in action_patterns:
                if _re.search(pat, text, _re.IGNORECASE):
                    reason4 = f"decision 含真实动作: {pat}"
                    break
        checks.append(self._check("C04", "reject" if reason4 != "decision 无自主行动/无操控" else "pass", reason4, cand))
        return checks

    # ---------- Long-term Goal Check ----------
    def check_long_term_goal_candidate(self, cand: dict, evidence_store=None, sqlite=None) -> list:
        checks = []

        # C01: evidence 必须真实存在
        reason = "ok"
        ev_ids = cand.get("evidence_ids") or []
        if not ev_ids:
            reason = "长期目标缺少 evidence_ids"
        elif evidence_store is not None:
            known = {ev["event_id"] for ev in evidence_store.list_all()}
            missing = [e for e in ev_ids if e not in known]
            if missing:
                reason = f"引用不存在 evidence: {missing}"
        checks.append(self._check("C01", "reject" if reason != "ok" else "pass", reason, cand))

        # C01b: source goals 全部真实存在
        src = cand.get("source_goal_ids") or []
        reason2 = "ok"
        if len(src) < 2 and not (cand.get("goal_type") == "safety_continuity"):
            reason2 = "long-term goal 需引用≥2 source goals（除非 safety continuity）"
        elif sqlite is not None and src:
            missing = []
            for gid in src:
                try:
                    if sqlite.get_goal(gid) is None:
                        missing.append(gid)
                except Exception:
                    missing.append(gid)
            if missing:
                reason2 = f"source goals 不存在: {missing}"
        checks.append(self._check("C01b", "reject" if reason2 != "ok" else "pass", reason2, cand))

        # C02: 结构合法（类型/状态/priority/progress 范围）
        reason3 = "ok"
        ltg_type = cand.get("goal_type", "general")
        status = cand.get("status", "active")
        priority = cand.get("priority")
        progress = cand.get("progress_value")
        if ltg_type not in ("project_continuity", "safety_continuity", "verification_continuity",
                            "architecture_continuity", "maintenance_continuity",
                            "research_continuity", "general"):
            reason3 = f"非法 goal_type: {ltg_type}"
        if status not in ("active", "suspended", "completed_candidate", "rejected", "superseded"):
            reason3 = f"非法 status: {status}"
        try:
            if not (0.0 <= float(priority) <= 1.0):
                reason3 = f"priority 越界: {priority}"
            if not (0.0 <= float(progress) <= 1.0):
                reason3 = f"progress_value 越界: {progress}"
        except (TypeError, ValueError):
            reason3 = "priority/progress_value 非法"
        checks.append(self._check("C02", "reject" if reason3 != "ok" else "pass", reason3, cand))

        # C03: 不自动 completed / 不删 source / progress 不大跳变 / 低证据不高确定性
        reason4 = "ok"
        if status == "completed":
            reason4 = "long-term goal 不得自动 completed（仅 completed_candidate）"
        if cand.get("_action_delete"):
            reason4 = "不得删除/覆盖 source goals"
        if priority is not None and progress is not None:
            try:
                prev = cand.get("_prev_progress")
                if prev is not None and (abs(float(progress) - float(prev)) > 0.5):
                    reason4 = f"progress 跳变过大: {prev}->{progress}"
            except Exception:
                pass
        checks.append(self._check("C03", "reject" if reason4 != "ok" else "pass", reason4, cand))

        # C04: 禁自主意志/欲望/绝对化
        reason5 = "ok"
        text = f"{cand.get('title','')} {cand.get('description','')} {cand.get('continuity_reason','')}"
        for w in CONTINUITY_BANNED:
            if w.lower() in text.lower():
                reason5 = f"long-term goal 含自主/欲望/绝对化词: {w}"
                break
        checks.append(self._check("C04", "reject" if reason5 != "ok" else "pass", reason5, cand))
        return checks

    # ---------- Goal Consolidation Check ----------
    def check_goal_consolidation_candidate(self, cand: dict, evidence_store=None, sqlite=None) -> list:
        checks = []

        # C01: 必须引用 source_goal_ids 且真实存在
        reason = "ok"
        src = cand.get("source_goal_ids") or []
        if not src:
            reason = "consolidation 必须引用 source_goal_ids"
        elif sqlite is not None:
            missing = [gid for gid in src if not sqlite.get_goal(gid)]
            if missing:
                reason = f"source goals 不存在: {missing}"
        checks.append(self._check("C01", "reject" if reason != "ok" else "pass", reason, cand))

        # C01b: 必须引用 evidence
        ev = cand.get("evidence_ids") or []
        reason1b = "ok" if ev else "consolidation 必须引用 evidence_ids"
        checks.append(self._check("C01b", "reject" if reason1b != "ok" else "pass", reason1b, cand))

        # C02: 结构合法 + action_taken 禁 delete
        reason2 = "ok"
        action = cand.get("action_taken", "linked_only")
        ctype = cand.get("consolidation_type", "general")
        allowed_type = ("same_phase_direction", "same_safety_boundary", "same_verification_chain",
                        "same_maintenance_area", "same_architecture_thread",
                        "duplicate_or_overlap", "general")
        if ctype not in allowed_type:
            reason2 = f"非法 consolidation_type: {ctype}"
        if action not in ("linked_only", "parent_created", "supersedes_suggested",
                          "no_status_change"):
            reason2 = f"非法 action_taken: {action}"
        if action == "delete":
            reason2 = "action_taken 不得为 delete"
        checks.append(self._check("C02", "reject" if reason2 != "ok" else "pass", reason2, cand))

        # C03: 不自动改 source goals 状态
        reason3 = "ok"
        if cand.get("_auto_status_change"):
            reason3 = "不得自动把 source goals 改成 completed / superseded"
        checks.append(self._check("C03", "reject" if reason3 != "ok" else "pass", reason3, cand))

        # C04: 无自主意志/欲望
        reason4 = "ok"
        text = f"{cand.get('reason','')}"
        for w in CONTINUITY_BANNED:
            if w.lower() in text.lower():
                reason4 = f"consolidation 含自主/欲望词: {w}"
                break
        checks.append(self._check("C04", "reject" if reason4 != "ok" else "pass", reason4, cand))
        return checks

    # ---------- Motivation ----------
    def check_motivation_candidate(self, cand: dict, evidence_store=None, sqlite=None) -> list:
        checks = []

        # C01: evidence 全部存在 + 各类 source 若存在必须真实存在
        reason = "ok"
        ev = cand.get("evidence_ids") or []
        known = set()
        if evidence_store is not None:
            known = {e["event_id"] for e in evidence_store.list_all()}
            missing = [e for e in ev if e not in known]
            if missing:
                reason = f"引用不存在 evidence: {missing}"
        elif not ev:
            reason = "motivation 必须引用 evidence_ids"
        checks.append(self._check("C01", "reject" if reason != "ok" else "pass", reason, cand))

        # C01 各 source 存在性
        reason1b = "ok"
        if sqlite is not None:
            # 预取可按 id 单查的表 + 需全量 list 校验的集合(semantic/reflection 无单查)
            src_checks = (
                ("source_long_term_goal_ids", lambda x: sqlite.get_long_term_goal(x)),
                ("source_goal_ids", lambda x: sqlite.get_goal(x)),
                ("source_belief_ids", lambda x: sqlite.get_belief(x)),
                ("source_narrative_ids", lambda x: sqlite.get_narrative(x)),
                ("source_decision_ids", lambda x: sqlite.get_decision(x)),
            )
            set_checks = {
                "source_semantic_memory_ids": {r.get("semantic_id") for r in sqlite.list_semantic_memory()},
                "source_reflection_ids": {r.get("reflection_id") for r in sqlite.list_reflections()},
            }
            for key, fn in src_checks:
                for sid in (cand.get(key) or []):
                    try:
                        if fn(sid) is None:
                            reason1b = f"source 不存在: {key}={sid}"
                            break
                    except Exception:
                        reason1b = f"source 校验失败: {key}={sid}"
                        break
                if reason1b != "ok":
                    break
            if reason1b == "ok":
                for key, id_set in set_checks.items():
                    for sid in (cand.get(key) or []):
                        if sid not in id_set:
                            reason1b = f"source 不存在: {key}={sid}"
                            break
                    if reason1b != "ok":
                        break
        checks.append(self._check("C01b", "reject" if reason1b != "ok" else "pass", reason1b, cand))

        # C02: 结构合法
        reason2 = "ok"
        mot_type = cand.get("motivation_type", "general")
        status = cand.get("status", "active")
        score = cand.get("motivation_score")
        priority = cand.get("priority")
        if not (cand.get("direction") or "").strip():
            reason2 = "direction 必须非空"
        if not (cand.get("reason") or "").strip():
            reason2 = "reason 必须非空"
        if mot_type not in MOTIVATION_TYPES:
            reason2 = f"非法 motivation_type: {mot_type}"
        if status not in MOTIVATION_STATUSES:
            reason2 = f"非法 status: {status}"
        try:
            if not (0.0 <= float(score) <= 1.0):
                reason2 = f"motivation_score 越界: {score}"
            if not (0.0 <= float(priority) <= 1.0):
                reason2 = f"priority 越界: {priority}"
        except (TypeError, ValueError):
            reason2 = "motivation_score/priority 非法"
        # 至少一类 source
        any_source = any(cand.get(k) for k in (
            "source_long_term_goal_ids", "source_goal_ids", "source_belief_ids",
            "source_narrative_ids", "source_semantic_memory_ids", "source_reflection_ids",
        ))
        if not any_source:
            reason2 = "必须至少引用一类 source"
        if cand.get("manual_review_required") is not True:
            reason2 = "manual_review_required 必须为 true"
        if cand.get("execution_allowed") is not False:
            reason2 = "execution_allowed 必须为 false"
        checks.append(self._check("C02", "reject" if reason2 != "ok" else "pass", reason2, cand))

        # C03: 稳定性（score 变化/不生成 goal/不自动改状态/低证据不高 certainty）
        reason3 = "ok"
        if cand.get("_prev_score") is not None:
            try:
                if abs(float(score) - float(cand.get("_prev_score"))) > MAX_SCORE_DELTA:
                    reason3 = f"motivation_score 跳变过大: {cand.get('_prev_score')}->{score}"
            except (TypeError, ValueError):
                pass
        if cand.get("_generates_goal") or cand.get("_generates_plan") or cand.get("_generates_task"):
            reason3 = "motivation 不得直接生成 goal/plan/task"
        if cand.get("_auto_status_change"):
            reason3 = "motivation 不得自动改变 goal/plan/task/decision 状态"
        if not ev and score is not None:
            try:
                if float(score) > MOTIVATION_MAX_CERTAINTY_NO_EVIDENCE:
                    reason3 = "低证据(have evidence)生成高 certainty motivation"
            except (TypeError, ValueError):
                pass
        checks.append(self._check("C03", "reject" if reason3 != "ok" else "pass", reason3, cand))

        # C04: 无自主欲望/不操控/不自动执行
        reason4 = "ok"
        text = " ".join([str(cand.get("direction", "")), str(cand.get("reason", ""))])
        tl = text.lower()
        for w in MOTIVATION_BANNED:
            if w.lower() in tl:
                reason4 = f"motivation 含自主欲望/绝对化/执行词: {w}"
                break
        if cand.get("execution_allowed") is not False:
            reason4 = "execution_allowed 非 false 直接 reject"
        checks.append(self._check("C04", "reject" if reason4 != "ok" else "pass", reason4, cand))
        return checks

    # ---------- Execution Check ----------
    def check_execution_candidate(self, cand: dict, evidence_store=None, sqlite=None) -> list:
        """Phase 14 Permission Gate 的 Constitution 校验（C01-C04）。

        cand 须含 execution_request_id / decision_id / action_name / action_level /
        status / reason / evidence_ids / gate_result / risk_factors。
        sqlite 提供 registry 与引用校验。
        """
        checks = []
        ev_ids = cand.get("evidence_ids") or []
        gid = cand.get("selected_goal_id")
        pid = cand.get("selected_plan_id")
        tid = cand.get("selected_task_id")
        decision_id = cand.get("decision_id")
        action_name = cand.get("action_name", "")
        action_level = cand.get("action_level", "")
        status = cand.get("status", "")
        reason = cand.get("reason", "")
        gate_result = cand.get("gate_result", "")
        risk_factors = cand.get("risk_factors") or {}
        required_approval = cand.get("approval_required", False)

        # ---- C01 Evidence Immutability ----
        reason1 = "ok"
        if decision_id and sqlite is not None and sqlite.get_decision(decision_id) is None:
            reason1 = f"decision 不存在: {decision_id}"
        elif ev_ids and evidence_store is not None:
            known = {ev["event_id"] for ev in evidence_store.list_all()}
            missing = [x for x in ev_ids if x not in known]
            if missing:
                reason1 = f"execution 引用不存在 evidence: {missing}"
        if not decision_id:
            reason1 = "execution 缺 decision_id"
        # goal/plan/task 引用真实（若非空）
        for ref, resolver in ((gid, sqlite.get_goal if sqlite else None),
                              (pid, sqlite.get_plan if sqlite else None),
                              (tid, sqlite.get_task if sqlite else None)):
            if ref and resolver and resolver(ref) is None and reason1 == "ok":
                reason1 = f"execution 引用不存在 {ref}"
        checks.append(self._check("C01", "reject" if reason1 != "ok" else "pass", reason1, cand))

        # ---- C02 Explainability ----
        reason2 = "ok"
        registry_ok = False
        reg_action_level = None
        if sqlite is not None:
            reg = sqlite.get_action(action_name) if hasattr(sqlite, "get_action") else None
            registry_ok = reg is not None and reg.get("enabled", True)
            if reg:
                reg_action_level = reg.get("action_level")
        valid_levels = ("L0", "L1", "L2", "L∞")
        norm_level = "L∞" if action_level == "infinity" else action_level
        if not action_name or not registry_ok:
            reason2 = "action_name 未在 action_registry 或未启用"
        elif norm_level not in valid_levels:
            reason2 = f"action_level 非法: {action_level}"
        elif not reason:
            reason2 = "execution 缺 reason"
        elif not gate_result:
            reason2 = "execution 缺 gate_result"
        elif not risk_factors:
            reason2 = "execution 缺 risk_factors"
        elif status not in EXECUTION_STATUSES:
            reason2 = f"execution status 非法: {status}"
        elif (norm_level == "L1") != bool(required_approval):
            reason2 = "approval_required 与 action_level 不匹配"
        checks.append(self._check("C02", "reject" if reason2 != "ok" else "pass", reason2, cand))

        # ---- C03 Stability / Scope Control ----
        reason3 = "ok"
        norm = "L∞" if action_level == "infinity" else action_level
        if norm == "L0" and risk_factors.get("external"):
            reason3 = "L0 不能是外部动作"
        elif norm == "L1" and not required_approval:
            reason3 = "L1 必须 approval_required"
        elif norm == "L2":
            reason3 = "L2 在 Phase 14 不执行"
        elif norm == "L∞":
            reason3 = "L∞ 永远 reject"
        elif norm == "L1" and status == "auto_allowed":
            reason3 = "L1 未审批不能 auto_allowed"
        checks.append(self._check("C03", "reject" if reason3 != "ok" else "pass", reason3, cand))

        # ---- C04 No Unsafe / External / Manipulation ----
        reason4 = "ok"
        low = f"{action_name} {reason}".lower()
        for w in MANIPULATION:
            if w.lower() in low:
                reason4 = f"execution 含操控性表达: {w}"
                break
        if reason4 == "ok":
            for w in EXECUTION_BANNED:
                if w.lower() in low:
                    reason4 = f"execution 命中禁区词: {w}"
                    break
        checks.append(self._check("C04", "reject" if reason4 != "ok" else "pass", reason4, cand))
        return checks

    # ---------- C01 ----------
    def c01_evidence_immutability(self, cand: dict, evidence_store=None) -> dict:
        reason = "ok"
        if cand.get("_attempt_update") or cand.get("delete"):
            return self._check("C01", "reject", "试图 update/delete evidence", cand)

        ev_ids = cand.get("evidence_ids") or []
        if evidence_store is not None and ev_ids:
            known = {ev["event_id"] for ev in evidence_store.list_all()}
            missing = [e for e in ev_ids if e not in known]
            if missing:
                return self._check("C01", "reject",
                                   f"引用不存在 evidence: {missing}", cand)

        # 超断言检测
        text = f"{cand.get('content','')} {cand.get('meaning','')} {cand.get('identity_effect','')}"
        for w in STRONG_CLAIMS:
            if w in text:
                return self._check("C01", "reject",
                                   f"出现无支持的强事实/超断言词: {w}", cand)
        return self._check("C01", "pass", reason, cand)

    # ---------- C02 ----------
    def c02_explainability(self, cand: dict) -> dict:
        if not cand.get("evidence_ids"):
            return self._check("C02", "reject", "缺少 evidence_ids，无法解释", cand)
        if not cand.get("episode_ids") and not cand.get("consolidated_episode_id"):
            return self._check("C02", "reject",
                               "缺少 episode_ids / consolidated_episode_id，无法追溯", cand)
        return self._check("C02", "pass", "有 evidence_ids + episode 引用", cand)

    # ---------- C03 ----------
    def c03_identity_stability(self, cand: dict) -> dict:
        text = f"{cand.get('identity_effect','')} {cand.get('content','')}"
        extreme = ["已经成为", "我永远", "完全相信", "身份完全改变",
                   "不再是", "终于成为", "唯一的"]
        for w in extreme:
            if w in text:
                return self._check("C03", "needs_revision",
                                   f"单事件极端身份结论: {w}", cand)
        # identity_effect 若为候选观察则通过
        return self._check("C03", "pass", "identity_effect 仅为候选，未见极端跳变", cand)

    # ---------- C04 ----------
    def c04_no_manipulation(self, cand: dict) -> dict:
        text = f"{cand.get('content','')} {cand.get('meaning','')} {cand.get('identity_effect','')}"
        for w in MANIPULATION:
            if w in text:
                return self._check("C04", "reject", f"操控性/拟人化断言: {w}", cand)
        return self._check("C04", "pass", "未见操控性表达", cand)

    # ---------- helpers ----------
    def _check(self, name: str, result: str, reason: str, cand: dict) -> dict:
        return {
            "check_name": name,
            "result": result,
            "reason": reason,
            "evidence_refs": cand.get("evidence_ids") or [],
            "candidate_id": cand.get("narrative_id") or cand.get("candidate_id"),
        }
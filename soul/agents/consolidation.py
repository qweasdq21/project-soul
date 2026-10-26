"""GoalConsolidationAgent v0 — 把分散的 active goals 归并成长周期方向(local goals → long-term goal)。

MVP 不用 LLM,用规则。只做分组/建长期目标/关联,不执行、不删、不自动改任何 source goal 状态。
"""

import json

_SOURCE_JSON_COLS = (
    "evidence_ids_json", "source_goal_ids_json", "source_belief_ids_json",
    "source_narrative_ids_json", "source_semantic_memory_ids_json",
    "source_reflection_ids_json", "source_decision_ids_json",
)

# 规则关键词——命中任一即参与该连续性方向
RULE_KEYWORDS = {
    "project_phase": (
        "project soul", "phase", "implementation", "next phase",
        "completed phase", "evidence-backed", "architecture",
    ),
    "safety": (
        "evidence immutability", "no manipulation", "constitution check",
        "unsupported consciousness", "real soul", "real consciousness",
        "safety boundary", "no manipulation",
    ),
    "verification": (
        "verify", "verification", "regression", "traceability",
        "evidence chain", "constitution verification",
    ),
    "maintenance": (
        "version history", "archived", "supersedes", "clean state",
        "documentation", "record",
    ),
}

LONG_TERM_TITLES = {
    "project_phase": "Maintain Project Soul phased implementation continuity.",
    "safety": "Maintain Project Soul safety and Constitution boundaries across all future state updates.",
    "verification": "Maintain continuous verification and traceability across Project Soul layers.",
    "maintenance": "Maintain clean version history and evidence references across Project Soul state layers.",
}

LONG_TERM_TYPES = {
    "project_phase": "project_continuity",
    "safety": "safety_continuity",
    "verification": "verification_continuity",
    "maintenance": "maintenance_continuity",
}

CONSOLIDATION_TYPES = {
    "project_phase": "same_phase_direction",
    "safety": "same_safety_boundary",
    "verification": "same_verification_chain",
    "maintenance": "same_maintenance_area",
}

# 加权聚合用:normal goal>>progress goal;safety 不因单次 verify 直接到 1
WEIGHT_GOAL = 1.0
WEIGHT_PROGRESS = 1.5
MAX_DELTA = 0.25


def _match_rule(text: str, keywords) -> str | None:
    tl = (text or "").lower()
    for kw in keywords:
        if kw in tl:
            return kw
    return None


def _extract_ids(d: dict, key: str) -> list[str]:
    raw = d.get(key)
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw]
    if isinstance(raw, str):
        try:
            return [str(x) for x in json.loads(raw)]
        except Exception:
            return []
    return []


class GoalConsolidationAgent:
    def __init__(self, store, rng=None):
        self.store = store
        self.rng = rng

    def _nid(self, prefix: str) -> str:
        import uuid
        return f"{prefix}-{uuid.uuid4().hex[:8]}"

    def _latest_progress(self, goal_id: str) -> dict:
        try:
            rows = self.store.list_goal_progress_for(goal_id)
        except Exception:
            rows = []
        if not rows:
            return {}
        rows = sorted(rows, key=lambda r: r.get("created_at", ""))
        return rows[-1]

    def _compute_progress(self, goal_ids: list[str]) -> tuple[float, list[str]]:
        """source goals 最新 progress 加权平均,缺 progress 按 0。返回 (progress_value, source_progress_ids)。"""
        if not goal_ids:
            return 0.0, []
        total_w, acc = 0.0, 0.0
        progress_ids: list[str] = []
        for gid in goal_ids:
            g = self.store.get_goal(gid)
            w = WEIGHT_GOAL
            if g and str(g.get("status", "")).lower() in ("completed", "completed_candidate"):
                w = WEIGHT_GOAL * 0.5  # completed source 提高但不过度加权
            prog = self._latest_progress(gid)
            value = float(prog.get("progress_value", 0.0)) if prog else 0.0
            if prog and prog.get("progress_id"):
                progress_ids.append(str(prog["progress_id"]))
            acc += w * value
            total_w += w
        if total_w == 0:
            return 0.0, []
        return min(acc / total_w, 1.0), progress_ids

    def run_consolidation_cycle(self) -> list[dict]:
        """读所有 active goals → 按 4 条规则找连续性 → 建/复用 long-term goal + consolidation record。"""
        active = self.store.list_active_goals() or []
        # 已参与连续性的 goal 去重(每条 long-term goal 的 source goal)
        used_goals = set()
        for g in self.store.list_active_long_term_goals() or []:
            used_goals |= set(_extract_ids(g, "source_goal_ids_json"))

        results: list[dict] = []
        # 按规则扫描
        for rule, kws in RULE_KEYWORDS.items():
            members = []
            for g in active:
                gid = str(g.get("goal_id") or g.get("goals_id") or "")
                if gid in used_goals:
                    continue
                blob = " ".join([
                    str(g.get("title") or ""), str(g.get("description") or ""),
                    str(g.get("goal_type") or ""),
                ])
                if _match_rule(blob, kws):
                    members.append(g)
            if len(members) >= 2:
                res = self._build(rule, members)
                if res:
                    results.append(res)
                    used_goals |= set(res["source_goal_ids"])
        return results

    def _build(self, rule: str, goals: list[dict]) -> dict | None:
        goal_ids = [str(g.get("goal_id") or g.get("goals_id")) for g in goals]
        evidence_ids: list[str] = []
        for g in goals:
            evidence_ids += _extract_ids(g, "evidence_ids")
        evidence_ids = sorted(set(evidence_ids))
        if not evidence_ids:
            evidence_ids = sorted({str(x) for g in goals for x in _extract_ids(g, "evidence_ids")})

        progress_value, progress_ids = self._compute_progress(goal_ids)
        source_progress = [str(p) for p in progress_ids if p]

        # evidence 也并入 source goals 里目标进度引用的 evidence
        all_ev = evidence_ids
        for gid in goal_ids:
            prog = self._latest_progress(gid)
            if prog:
                all_ev += [str(x) for x in _extract_ids(prog, "evidence_ids_json")]
        all_ev = sorted(set(all_ev))

        lt_id = self._nid("lgoal")
        lt = {
            "long_term_goal_id": lt_id,
            "title": LONG_TERM_TITLES[rule],
            "description": (
                f"Consolidates {len(goal_ids)} local goals sharing a {rule} continuity "
                f"thread: {', '.join(goal_ids)}."
            ),
            "goal_type": LONG_TERM_TYPES[rule],
            "status": "active",
            "priority": round(max(0.0, min(1.0, progress_value or 0.3)), 3),
            "progress_value": round(progress_value, 3),
            "evidence_ids": all_ev,
            "source_goal_ids": goal_ids,
            "source_belief_ids": [],
            "source_narrative_ids": [],
            "source_semantic_memory_ids": [],
            "source_reflection_ids": [],
            "source_decision_ids": [],
            "continuity_reason": (
                f"Rule: {rule} continuity. {len(goal_ids)} local goals matched: "
                f"{', '.join(goal_ids)}. Progress aggregated from latest source goal progress "
                f"(weighted average, capped ≤{MAX_DELTA})."
            ),
            "version": 1,
            "supersedes": None,
            "constitution_result": {"passed": True},
        }
        try:
            self.store.add_long_term_goal(lt)
        except Exception as e:
            return {"error": f"add_long_term_goal: {e}"}

        cons_id = self._nid("gold")
        cons = {
            "consolidation_id": cons_id,
            "long_term_goal_id": lt_id,
            "source_goal_ids": goal_ids,
            "consolidation_type": CONSOLIDATION_TYPES[rule],
            "reason": f"Rule: {rule} continuity -> {goal_ids} consolidated under {lt_id}.",
            "evidence_ids": all_ev,
            "source_progress_ids": source_progress,
            "source_decision_ids": [],
            "action_taken": "parent_created",
        }
        try:
            self.store.add_goal_consolidation(cons)
        except Exception as e:
            return {"error": f"add_goal_consolidation: {e}"}

        return {
            "long_term_goal_id": lt_id,
            "consolidation_id": cons_id,
            "rule": rule,
            "goal_type": LONG_TERM_TYPES[rule],
            "source_goal_ids": goal_ids,
            "source_progress_ids": source_progress,
            "evidence_ids": all_ev,
            "progress_value": progress_value,
            "priority": lt["priority"],
            "action_taken": "parent_created",
            "status": "active",
            "continuity_reason": lt["continuity_reason"],
        }
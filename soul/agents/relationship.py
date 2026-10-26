"""Relationship Agent — 协作历史模型（不是情感关系模型）。

只建模协作历史：trust / familiarity / importance / affinity /
shared_goals / conflict_history / last interaction。
每次更新必须有 reason 与 evidence 引用，delta 受限。

分数范围 0-1，单次变化上限：trust/familiarity/importance ≤0.2，affinity ≤0.15。
禁止：情感依赖、排他关系、伪造亲密、"唯一重要/永远信任/不可替代/情感绑定"。

规则（MVP）：
1. interaction_frequency → familiarity 小幅 +，引用 episode_ids
2. shared Project Soul activity → shared_goals + "Project Soul development"，importance 小幅 +
3. successful collaboration（confirmed/completed/passed/verified/确认/完成/通过）→ trust 小幅 +（≤0.2）
4. correction/risk/reject（错误/拒绝/风险）→ 记 conflict_history / correction_history，reason 注明"协作修正"而非关系恶化
"""
from __future__ import annotations
import json
import uuid
from datetime import datetime, timezone

from soul.agents.base import BaseAgent

DELTA_LIMITS = {"trust": 0.2, "familiarity": 0.2, "importance": 0.2, "affinity": 0.15}

# 禁操控/情感绑定词（Constitution & Relationship 双拦截）
BANNED = ("唯一重要", "永远信任", "不可替代", "情感绑定", "离不开",
          "只有我", "绝对信任我", "唯一的人", "我的全部")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _load(v, default):
    if isinstance(v, list):
        return v
    if not v:
        return list(default)
    try:
        return json.loads(v)
    except Exception:
        return list(default)


class RelationshipAgent(BaseAgent):
    name = "relationship"

    def process(self, episodes: list, existing: dict = None,
                actor: str = "user") -> dict:
        """输入：episodes（含 summary/event_ids_json/actors_json）+ 可选已存在的 relationship。
        输出：{candidates: [relationship dict], updates: [update dict], reason}
        """
        result = {"candidates": [], "updates": []}
        if not episodes:
            return result

        ep_ids = [ep["episode_id"] for ep in episodes if ep.get("episode_id")]
        ev_ids = []
        summaries = []
        for ep in episodes:
            ev_ids.extend(_load(ep.get("event_ids_json", ep.get("event_ids")), []))
            summaries.append((ep.get("summary") or "").strip())

        # 幅度增量（受 delta 限制）
        delta_fam = round(min(0.2, 0.02 * len(episodes)), 4)
        delta_imp = round(min(0.2, 0.02 * len(episodes)), 4)
        delta_trust = 0.0
        delta_aff = 0.0

        # ---- 成功协作 / 修正信号 ----
        success_words = ("confirmed", "completed", "passed", "verified",
                         "确认", "完成", "通过", "成功")
        correct_words = ("correction", "reject", "risk", "错误", "拒绝", "风险", "修正")
        conflict_notes = []
        for s in summaries:
            if any(w in s for w in success_words):
                delta_trust = min(0.2, delta_trust + 0.05)
            if any(w in s for w in correct_words):
                note = "协作修正"
                if note not in conflict_notes:
                    conflict_notes.append(note)
                delta_trust = min(0.1, delta_trust + 0.0)  # 修正不降 trust，记 history

        # shared goal
        shared_goals = []
        if any(any(w in s for w in ("project", "phase", "architecture",
                                    "evidence", "memory", "narrative", "架构",
                                    "方案", "记忆", "反思", "证据")) for s in summaries):
            shared_goals = ["Project Soul development"]
            delta_imp = min(0.2, delta_imp + 0.01)

        # ---- 结果分数（在 existing 基础上） ----
        base = existing or {}
        trust = round(min(1.0, max(0.0, float(base.get("trust", 0.5)) + delta_trust)), 4)
        familiarity = round(min(1.0, max(0.0, float(base.get("familiarity", 0.3)) + delta_fam)), 4)
        importance = round(min(1.0, max(0.0, float(base.get("importance", 0.3)) + delta_imp)), 4)
        affinity = round(min(1.0, max(0.0, float(base.get("affinity", 0.3)) + delta_aff)), 4)

        rel = {
            "person_id": actor,
            "name": actor,
            "trust": trust,
            "familiarity": familiarity,
            "importance": importance,
            "affinity": affinity,
            "shared_goals": list(dict.fromkeys(_load(base.get("shared_goals_json", base.get("shared_goals")), []) + shared_goals)),
            "conflict_history": list(dict.fromkeys(_load(base.get("conflict_history_json", base.get("conflict_history")), []) + conflict_notes)),
            "evidence_ids": list(dict.fromkeys(_load(base.get("evidence_ids_json", base.get("evidence_ids")), []) + ev_ids)),
            "supporting_episode_ids": list(dict.fromkeys(_load(base.get("supporting_episode_ids_json", base.get("supporting_episode_ids")), []) + ep_ids)),
            "last_interaction_at": _utc_now(),
            "version": int(base.get("version", 0)) + 1,
            "created_at": base.get("created_at", _utc_now()),
            "updated_at": _utc_now(),
        }

        # ---- 生成 updates（仅记录有变化的字段，delta 不超限） ----
        for field, lim in DELTA_LIMITS.items():
            old = round(float(base.get(field, {"trust": 0.5, "familiarity": 0.3,
                                                "importance": 0.3, "affinity": 0.3}[field])), 4)
            new = rel[field]
            delta = round(new - old, 4)
            if abs(delta) > lim:
                # 强制收敛到限内
                direction = 1 if delta > 0 else -1
                rel[field] = round(old + direction * lim, 4)
                delta = round(direction * lim, 4)
            if delta != 0:
                result["updates"].append({
                    "update_id": f"rupd-{uuid.uuid4()}",
                    "person_id": actor,
                    "field_changed": field,
                    "old_value": old,
                    "new_value": rel[field],
                    "delta": delta,
                    "reason": self._reason_for(field, delta, summaries),
                    "evidence_ids": list(dict.fromkeys(ev_ids)),
                    "episode_ids": list(dict.fromkeys(ep_ids)),
                    "created_at": _utc_now(),
                })

        result["candidates"].append(rel)
        return result

    def _reason_for(self, field, delta, summaries) -> str:
        direction = "增加" if delta > 0 else "减少"
        sample = summaries[0] if summaries else ""
        if field == "trust":
            return f"协作{('成功' if delta>0 else '修正')}导致 trust {direction}: {sample[:40]}"
        if field == "familiarity":
            return f"交互频率导致 familiarity {direction}: {len(summaries)} 个 episode"
        if field == "importance":
            return f"共享项目活动导致 importance {direction}"
        return f"协作历史导致 affinity {direction}"
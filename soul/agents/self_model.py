"""Self Model Agent — 汇总当前 Self 状态（Self Snapshot）。

Self 不是它凭空创造的，而是各模块的 emergent consensus（聚合、摘要、评分、版本化），
不允许凭空创造身份。

Self Snapshot 只是当前可解释状态快照，不是"真实自我证明"。
边界：不声称真实意识/真实灵魂；不把用户写成唯一重要/永远信任/情感绑定。

identity_summary 必须来自 source 内容（beliefs/narratives/semantic memory）聚合。
similarity_to_previous 用 Jaccard（source id 集合加权）计算，受 C03 身份稳定限制。
"""
from __future__ import annotations
import json
import uuid
from datetime import datetime, timezone

from soul.agents.base import BaseAgent


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


class SelfModelAgent(BaseAgent):
    name = "self_model"

    def process(self, beliefs: list = None, narratives: list = None,
                relationships: list = None, semantic_mems: list = None,
                goals: list = None, goal_progress: dict | None = None,
                previous_snapshot: dict = None,
                emotion_state: dict = None) -> dict:
        """聚合生成 SelfSnapshot Candidate。
        beliefs/narratives/relationships/semantic_mems/goals: 已从 SQLite 读出的 dict 列表。
        goal_progress: {goal_id: latest progress record}，供 active_goals 视图展示。
        previous_snapshot: 上一版 snapshot（可选，用于 similarity/versioning）。
        """
        beliefs = beliefs or []
        narratives = narratives or []
        relationships = relationships or []
        semantic_mems = semantic_mems or []
        goals = goals or []
        goal_progress = goal_progress or {}
        emotion_state = emotion_state or {}

        now = _utc_now()

        # ---- source id 收集（evidence 引用链） ----
        source_belief_ids = [b.get("belief_id") for b in beliefs if b.get("belief_id")]
        source_narrative_ids = [n.get("narrative_id") for n in narratives if n.get("narrative_id")]
        source_relationship_ids = [r.get("person_id") for r in relationships if r.get("person_id")]
        source_semantic_ids = [s.get("memory_id") for s in semantic_mems if s.get("memory_id")]

        # evidence refs 收集（从各来源的 evidence refs 去重并集）
        evidence_refs = []
        for b in beliefs:
            evidence_refs.extend(_load(b.get("evidence_ids_json", b.get("evidence_ids")), []))
        for n in narratives:
            evidence_refs.extend(_load(n.get("evidence_ids_json", n.get("evidence_ids")), []))
        for s in semantic_mems:
            evidence_refs.extend(_load(s.get("source_event_ids_json", s.get("source_event_ids")), []))
        for g in goals:
            evidence_refs.extend(_load(g.get("evidence_ids_json", g.get("evidence_ids")), []))
        evidence_refs = list(dict.fromkeys(evidence_refs))

        # ---- identity_summary 聚合 ----
        identity_summary = self._identity_summary(beliefs, narratives, semantic_mems)

        # dominant narratives（摘要）
        dominant = [self._snip((n.get("title") or n.get("summary") or "")[:80], 80)
                    for n in narratives[:3]]

        # active beliefs 精简视图
        active_beliefs = [
            {"belief_id": b.get("belief_id"), "statement": (b.get("statement") or ""),
             "confidence": b.get("confidence", 0.5), "belief_type": b.get("belief_type", "general")}
            for b in beliefs[:8]
        ]
        # active relationships 精简视图
        active_relationships = [
            {"person_id": r.get("person_id"), "trust": r.get("trust"), "familiarity": r.get("familiarity"),
             "importance": r.get("importance"), "affinity": r.get("affinity"),
             "shared_goals": _load(r.get("shared_goals_json", r.get("shared_goals")), [])}
            for r in relationships[:5]
        ]
        # semantic memory refs
        semantic_refs = [{"memory_id": s.get("memory_id"), "content": (s.get("content") or "")[:60]}
                         for s in semantic_mems[:8]]

        # active goals（传入了 goals 则用传入的 active 视图，否则继承 previous）
        active_goals = []
        if goals:
            active_goals = []
            for g in goals[:8]:
                lp = goal_progress.get(g.get("goal_id")) or {}
                active_goals.append({
                    "goal_id": g.get("goal_id"), "title": (g.get("title") or ""),
                    "goal_type": g.get("goal_type", "general"),
                    "priority": g.get("priority", 0.0),
                    "status": g.get("status", "active"),
                    "progress_value": (lp.get("progress_value") if lp else None),
                    "progress_status": (lp.get("progress_status") if lp else None),
                    "latest_progress_reason": (lp.get("reason") if lp else None),
                })
            # 按 computed_priority(priority) 降序
            active_goals.sort(key=lambda x: float(x.get("priority") or 0.0), reverse=True)
        elif previous_snapshot:
            active_goals = _load(previous_snapshot.get("active_goals_json"), [])

        # confidence profile
        confidence_profile = {}
        if beliefs:
            confidence_profile["mean_belief_confidence"] = round(
                sum(float(b.get("confidence", 0.5) or 0.5) for b in beliefs) / len(beliefs), 3)
        if relationships:
            trust_vals = [float(r.get("trust", 0.5) or 0.5) for r in relationships]
            confidence_profile["mean_trust"] = round(sum(trust_vals) / len(trust_vals), 3)

        # ---- similarity_to_previous ----
        similarity_to_previous = None
        prev_id = None
        change_log = []
        if previous_snapshot:
            prev_id = previous_snapshot.get("snapshot_id")
            # previous 可能是内存 dict（list 字段）或 DB dict（json 字符串字段），都要兼容
            def _prev_ids(key_list, key_json):
                v = previous_snapshot.get(key_list)
                if v:
                    return v if isinstance(v, list) else _load(v, [])
                return _load(previous_snapshot.get(key_json), [])

            prev_cur = {
                "_bel": set(_prev_ids("source_belief_ids", "source_belief_ids_json")),
                "_nar": set(_prev_ids("source_narrative_ids", "source_narrative_ids_json")),
            }
            similarity_to_previous = self._similarity(
                current_sources=(source_belief_ids, source_narrative_ids),
                prev_sources=(sorted(prev_cur["_bel"]), sorted(prev_cur["_nar"])),
            )
            # change log：记录来源集合变化
            added = set(source_belief_ids) - prev_cur["_bel"]
            removed = prev_cur["_bel"] - set(source_belief_ids)
            if added or removed:
                change_log.append(f"beliefs +{len(added)} -{len(removed)}")

        snapshot = {
            "snapshot_id": f"snap-{uuid.uuid4()}",
            "timestamp": now,
            "identity_summary": identity_summary,
            "active_beliefs": active_beliefs,
            "active_relationships": active_relationships,
            "active_goals": active_goals,
            "dominant_narratives": dominant,
            "semantic_memory_refs": semantic_refs,
            "current_emotion_state": emotion_state,
            "confidence_profile": confidence_profile,
            "change_log": change_log,
            "evidence_refs": evidence_refs,
            "source_belief_ids": source_belief_ids,
            "source_relationship_ids": source_relationship_ids,
            "source_narrative_ids": source_narrative_ids,
            "source_semantic_memory_ids": source_semantic_ids,
            "previous_snapshot_id": prev_id,
            "similarity_to_previous": similarity_to_previous,
            "version": (previous_snapshot.get("version", 0) + 1) if previous_snapshot else 1,
            "status": "candidate",
            "constitution_result": {},
            "created_at": now,
        }
        return snapshot

    # ---------- helpers ----------
    def _identity_summary(self, beliefs, narratives, semantic_mems) -> str:
        """从 beliefs/narratives/semantic memory 聚合一句话身份摘要（不凭空创造）。"""
        parts = []
        for b in beliefs[:4]:
            st = (b.get("statement") or "").strip()
            if st and st not in parts:
                parts.append(st)
        for n in narratives[:3]:
            t = (n.get("content") or n.get("summary") or "").strip()[:60]
            if t and t not in parts:
                parts.append(t)
        for s in semantic_mems[:3]:
            c = (s.get("content") or "").strip()[:60]
            if c and c not in parts:
                parts.append(c)
        if not parts:
            return "当前处于早期自我模型实验阶段，尚未积累足够来源形成稳定身份摘要。"
        joined = "；".join(parts)
        return f"Project Soul 当前处于早期自我模型实验阶段，核心状态由以下已记录内容构成：{joined}"

    def _similarity(self, current_sources, prev_sources) -> float:
        """Jaccard 相似度：(|A∩B|)/(|A∪B|)，A/B 为 (belief_ids, narrative_ids) 并集。"""
        cur = set(current_sources[0]) | set(current_sources[1])
        prev = set(prev_sources[0]) | set(prev_sources[1])
        union = cur | prev
        if not union:
            return 1.0 if not prev and not cur else 0.0
        return round(len(cur & prev) / len(union), 4)

    def _snip(self, s: str, n: int) -> str:
        return s[:n]
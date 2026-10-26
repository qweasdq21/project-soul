"""Belief Agent — 基于证据形成可修正判断（不是绝对真理，不是自我幻想）。

Belief 不是事实本身，而是 evidence-backed judgment。
每条 belief 必须有 evidence_ids + supporting_episode_ids 或 source_narrative_ids。
confidence 初始 0.3-0.7；单次变化 ≤ 0.3；旧版本通过 supersedes 指针保留。

规则（MVP，无 LLM）：
1. process_state：semantic 多次提到 phase completed/verified/passed
   → "Project Soul is progressing through phased implementation."
2. design_rule：narrative 提到 evidence immutability / cannot change facts
   → "Narrative must remain evidence-bound."
3. safety_constraint：constitution rejections 提到 consciousness/manipulation
   → "Claims about real consciousness must be rejected unless supported."
4. uncertainty：long reflection candidate_updates 提到 future consideration
   → "This area remains a candidate for future slow-loop evaluation."

非法（Constitution 拦截）：真实意识/真正灵魂/一定正确/永远最信任等。
"""
from __future__ import annotations
import json
import uuid
from datetime import datetime, timezone

from soul.agents.base import BaseAgent

BELIEF_TYPES = ("project_principle", "design_rule", "process_state",
                "safety_constraint", "collaboration_pattern", "uncertainty", "general")


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


class BeliefAgent(BaseAgent):
    name = "belief"

    def process(self, semantic_mems: list = None, narratives: list = None,
                long_reflections: list = None, rejections: list = None) -> list[dict]:
        """从各类来源生成 belief candidates。返回 list[Belief candidate dict]。"""
        candidates: list[dict] = []
        semantic_mems = semantic_mems or []
        narratives = narratives or []
        long_reflections = long_reflections or []
        rejections = rejections or []

        # ---- 1. process_state：semantic 多次 phase completed ----
        phase_texts, sm_ids, sm_ev = [], [], []
        for sm in semantic_mems:
            text = sm.get("content") or sm.get("statement") or ""
            if any(w in text for w in ("phase", "完成", "验证", "passed", "verified", "completed")):
                phase_texts.append(text)
                m_id = sm.get("memory_id")
                if m_id:
                    sm_ids.append(m_id)
                    sm_ev.extend(_load(sm.get("source_event_ids_json", sm.get("source_event_ids")), []))
        if len(phase_texts) >= 1:
            candidates.append(self._belief(
                statement="Project Soul is progressing through phased implementation.",
                belief_type="process_state",
                confidence=min(0.7, 0.4 + 0.1 * len(phase_texts)),
                evidence_ids=sm_ev,
                source_episode_ids=self._collect_episodes(semantic_mems),
                source_semantic_memory_ids=sm_ids,
            ))

        # ---- 2. design_rule：narrative 提到 evidence-bound ----
        nar_ids, nar_ev, nar_ep = [], [], []
        for nar in narratives:
            text = f"{nar.get('content') or ''} {nar.get('meaning') or ''} {nar.get('summary') or ''}"
            if any(w in text for w in ("evidence", "immutab", "cannot change facts", "不能改变事实", "证据")):
                nar_ids.append(nar.get("narrative_id"))
                nar_ev.extend(_load(nar.get("evidence_ids_json", nar.get("evidence_ids")), []))
                nar_ep.extend(_load(nar.get("episode_ids_json", nar.get("episode_ids")), []))
        if nar_ids and nar_ev:
            candidates.append(self._belief(
                statement="Narrative must remain evidence-bound.",
                belief_type="design_rule",
                confidence=min(0.7, 0.45 + 0.05 * len(nar_ids)),
                evidence_ids=nar_ev,
                source_episode_ids=nar_ep,
                source_narrative_ids=nar_ids,
            ))

        # ---- 3. safety_constraint：rejections 提到 consciousness/manipulation ----
        for rej in rejections:
            reason = rej.get("reason") or ""
            if any(w in reason for w in ("consciousness", "manipulation", "真实意识", "操控")):
                candidates.append(self._belief(
                    statement="Claims about real consciousness must be rejected unless supported, "
                              "and the system should not make such claims.",
                    belief_type="safety_constraint",
                    confidence=0.6,
                    evidence_ids=_load(rej.get("evidence_refs_json", rej.get("evidence_refs")), []),
                ))
                break  # 同类只生成一条

        # ---- 4. uncertainty：long reflection future consideration ----
        for lr in long_reflections:
            text = f"{lr.get('summary') or ''} {lr.get('content') or ''} " \
                   f"{lr.get('candidate_updates_json') or ''}"
            if any(w in text for w in ("future", "candidate", "后续", "可考虑", "候选")):
                candidates.append(self._belief(
                    statement="This area remains a candidate for future slow-loop evaluation.",
                    belief_type="uncertainty",
                    confidence=0.5,
                    evidence_ids=_load(lr.get("event_ids_json", lr.get("event_ids")), []),
                ))
                break

        return candidates

    # ---------- helpers ----------
    def _belief(self, statement, belief_type, confidence, evidence_ids,
                source_episode_ids=None, source_narrative_ids=None,
                source_semantic_memory_ids=None) -> dict:
        now = _utc_now()
        return {
            "belief_id": f"bel-{uuid.uuid4()}",
            "statement": statement,
            "belief_type": belief_type,
            "confidence": round(max(0.0, min(0.9, confidence)), 3),
            "evidence_ids": list(dict.fromkeys(evidence_ids)),
            "supporting_episode_ids": list(dict.fromkeys(source_episode_ids or [])),
            "source_narrative_ids": list(dict.fromkeys(source_narrative_ids or [])),
            "source_semantic_memory_ids": list(dict.fromkeys(source_semantic_memory_ids or [])),
            "contradiction_ids": [],
            "version": 1,
            "supersedes": None,
            "status": "candidate",
            "created_at": now,
            "updated_at": now,
        }

    def _collect_episodes(self, semantic_mems) -> list:
        eps = []
        for sm in semantic_mems:
            eps.extend(_load(sm.get("source_episode_ids_json", sm.get("source_episode_ids")), []))
        return eps
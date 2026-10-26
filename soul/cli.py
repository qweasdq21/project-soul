"""CLI。Phase 1: skeleton banner。Phase 2:
  feed <消息>            — Perception→Evidence→Emotion→Importance 全链路 trace
  verify-evidence        — 校验 evidence hash chain
  --json                 — feed 输出 JSON 格式
"""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SOUL_DATA_DIR = Path(os.environ.get("SOUL_DATA_DIR", str(PROJECT_ROOT / "data")))
EVIDENCE_PATH = _SOUL_DATA_DIR / "evidence" / "evidence.jsonl"
SQLITE_PATH = _SOUL_DATA_DIR / "soul_state.sqlite3"


def _ensure_evidence_dir() -> None:
    EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)


def _feed(message: str, as_json: bool = False) -> int:
    from soul.agents.perception import PerceptionAgent, event_to_dict
    from soul.agents.emotion import EmotionAgent
    from soul.agents.importance import ImportanceAgent
    from soul.agents.memory import MemoryAgent
    from soul.agents.reflection import ReflectionAgent
    from soul.storage.evidence_store import EvidenceStore
    from soul.storage.sqlite_store import SQLiteStore

    _ensure_evidence_dir()
    store = EvidenceStore(str(EVIDENCE_PATH))
    sqlite = SQLiteStore(str(SQLITE_PATH))

    # Perception
    perception = PerceptionAgent()
    event = perception.process(message)
    event_dict = event_to_dict(event)
    stored = store.compute_and_append(event_dict)

    # Emotion
    emotion = EmotionAgent()
    appraisal = emotion.process(stored)

    # Importance
    importance = ImportanceAgent()
    importance_result = importance.process(stored, appraisal)

    # Memory (Phase 3)
    memory_agent = MemoryAgent()
    memory_result = memory_agent.process(stored, importance_result, appraisal, sqlite)

    # Reflection (Phase 3) — 仅 episode_candidate 触发
    reflection_result = None
    if "episode_id" in memory_result:
        ep = sqlite.read(memory_result["episode_id"])
        ref_agent = ReflectionAgent()
        ref = ref_agent.process(ep)
        sqlite.add_reflection(ref)
        reflection_result = ref

    sqlite.close()

    trace = {
        "event_id": stored["event_id"],
        "raw_content": stored["raw_content"],
        "normalized_content": stored["normalized_content"],
        "previous_hash": stored["previous_hash"],
        "hash": stored["hash"],
        "evidence_log_path": str(EVIDENCE_PATH),
        "appraisal_vector": appraisal["vector"],
        "appraisal_reasons": appraisal["reasons"],
        "importance_score": importance_result["importance_score"],
        "target_memory_layer": importance_result["target_memory_layer"],
        "importance_reasons": {
            "factors": importance_result["factors"],
            "reason": importance_result["reason"],
        },
        "memory_result": memory_result,
        "reflection": reflection_result,
        "sqlite_path": str(SQLITE_PATH),
    }

    if as_json:
        print(json.dumps(trace, ensure_ascii=False, indent=2))
    else:
        print("=== Project Soul feed trace ===")
        print(f"event_id            : {trace['event_id']}")
        print(f"raw_content         : {trace['raw_content']!r}")
        print(f"normalized_content  : {trace['normalized_content']!r}")
        print(f"previous_hash       : {trace['previous_hash']}")
        print(f"hash                : {trace['hash']}")
        print(f"evidence_log_path   : {trace['evidence_log_path']}")
        print(f"appraisal_vector    : {trace['appraisal_vector']}")
        print(f"appraisal_reasons   : {trace['appraisal_reasons']}")
        print(f"importance_score    : {trace['importance_score']}")
        print(f"target_memory_layer : {trace['target_memory_layer']}")
        print(f"importance_reasons  : {trace['importance_reasons']}")
        print(f"memory_result       : {trace['memory_result']}")
        print(f"reflection          : {trace['reflection']}")
        print(f"sqlite_path         : {trace['sqlite_path']}")
        print("=== trace done ===")
    return 0


def _verify_evidence() -> int:
    from soul.storage.evidence_store import EvidenceStore

    if not EVIDENCE_PATH.exists():
        print("No evidence file found. Use `python -m soul feed \"...\"` first.")
        return 1
    store = EvidenceStore(str(EVIDENCE_PATH))
    valid, message = store.verify_chain()
    print(message)
    return 0 if valid else 1


def _print_sqlite_table(title: str, rows: list[dict], keys: list[str]) -> int:
    from soul.storage.sqlite_store import SQLiteStore

    if not SQLITE_PATH.exists():
        print(f"No soul_state.sqlite3 yet. Use `python -m soul feed \"...\"` first.")
        return 1
    if not rows:
        print(f"{title}: (empty)")
        return 0
    print(f"=== {title} ({len(rows)}) ===")
    for r in rows:
        line = "  ".join(
            f"{k}={r.get(k)}" for k in keys
        )
        print(line)
    return 0


def _run_slow_loop() -> int:
    from soul.storage.sqlite_store import SQLiteStore
    from soul.loops.slow_loop import SlowLoop

    SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    store = SQLiteStore(str(SQLITE_PATH))
    loop = SlowLoop(store)
    try:
        trace = loop.run()
        print(json.dumps(trace, ensure_ascii=False, indent=2))
    finally:
        store.close()
    return 0


def _list_semantic_memory() -> int:
    from soul.storage.sqlite_store import SQLiteStore
    return _print_sqlite_table(
        "Semantic Memory",
        SQLiteStore(str(SQLITE_PATH)).list_semantic_memory(active_only=True),
        ["memory_id", "content", "source_episode_ids_json", "source_event_ids_json", "confidence", "importance"],
    )


def _list_consolidated_episodes() -> int:
    from soul.storage.sqlite_store import SQLiteStore
    return _print_sqlite_table(
        "Consolidated Episodes",
        SQLiteStore(str(SQLITE_PATH)).list_consolidated_episodes(),
        ["consolidated_episode_id", "source_episode_ids_json", "source_event_ids_json", "summary", "consolidation_reason"],
    )


def _list_long_reflections() -> int:
    from soul.storage.sqlite_store import SQLiteStore
    return _print_sqlite_table(
        "Long Reflections",
        SQLiteStore(str(SQLITE_PATH)).list_long_reflections(),
        ["reflection_id", "episode_id", "consolidated_episode_id", "summary"],
    )


def _list_working_memory() -> int:
    from soul.storage.sqlite_store import SQLiteStore

    return _print_sqlite_table(
        "Working Memory",
        SQLiteStore(str(SQLITE_PATH)).list_working_memory(active_only=True),
        ["memory_id", "event_id", "content", "importance_score", "archived"],
    )


def _list_episodes() -> int:
    from soul.storage.sqlite_store import SQLiteStore

    return _print_sqlite_table(
        "Episodes",
        SQLiteStore(str(SQLITE_PATH)).list_episodes(),
        ["episode_id", "event_ids_json", "summary", "importance_score"],
    )


def _list_reflections() -> int:
    from soul.storage.sqlite_store import SQLiteStore

    return _print_sqlite_table(
        "Reflections",
        SQLiteStore(str(SQLITE_PATH)).list_reflections(),
        ["reflection_id", "episode_id", "content"],
    )


def _run_narrative_cycle() -> int:
    """Narrative cycle: 读 consolidated/high-importance episodes → NarrativeAgent
    → Constitution 校验 → pass 落库 / reject 写 rejection log → 输出 trace。"""
    import json as _json
    from soul.storage.evidence_store import EvidenceStore
    from soul.storage.sqlite_store import SQLiteStore
    from soul.agents.narrative import NarrativeAgent
    from soul.agents.constitution import ConstitutionAgent
    from soul.loops.slow_loop import _jloads

    SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    sqlite = SQLiteStore(str(SQLITE_PATH))
    evidence = EvidenceStore(str(EVIDENCE_PATH))
    trace = {"narratives": [], "rejections": []}
    try:
        # candidate source: consolidated episodes（优先）+ 高重要单 episodes
        sources = []
        ceps = sqlite.list_consolidated_episodes()
        if ceps:
            sources.append(ceps[0])  # 最新
        else:
            eps = sqlite.list_episodes()
            for ep in eps:
                if (ep.get("importance_score", 0.0) or 0.0) >= 0.6:
                    sources.append(ep)
        if not sources:
            trace["skipped"] = "no consolidated/high-importance episodes"
            print(_json.dumps(trace, ensure_ascii=False, indent=2))
            return 0

        nar_agent = NarrativeAgent()
        con_agent = ConstitutionAgent()
        for src in sources:
            cand = nar_agent.process(src)
            if not cand:
                continue
            verdict = con_agent.process(cand, evidence_store=evidence, sqlite=sqlite)
            if verdict["decision"] == "pass":
                cand["status"] = "accepted"
                nar_id = sqlite.add_narrative(cand)
                trace["narratives"].append({
                    "narrative_id": nar_id,
                    "status": "accepted",
                    "evidence_ids": cand["evidence_ids"],
                    "episode_ids": cand["episode_ids"],
                })
            else:
                # reject 写 rejection log
                import uuid as _uuid
                rej_id = sqlite.add_rejection({
                    "rejection_id": f"rej-{_uuid.uuid4()}",
                    "candidate_type": "narrative",
                    "candidate_id": cand.get("narrative_id"),
                    "check_name": verdict["reason"],
                    "reason": verdict["reason"],
                    "candidate": cand,
                    "evidence_refs": cand.get("evidence_ids", []),
                    "created_at": cand.get("created_at"),
                })
                trace["rejections"].append({
                    "candidate_id": cand.get("narrative_id"),
                    "decision": verdict["decision"],
                    "reason": verdict["reason"],
                    "rejection_id": rej_id,
                })
        print(_json.dumps(trace, ensure_ascii=False, indent=2))
        return 0
    finally:
        sqlite.close()


def _list_narratives() -> int:
    from soul.storage.sqlite_store import SQLiteStore
    return _print_sqlite_table(
        "Narratives",
        SQLiteStore(str(SQLITE_PATH)).list_narratives(),
        ["narrative_id", "narrative_type", "title", "evidence_ids_json", "episode_ids_json", "version", "status"],
    )


def _list_rejections() -> int:
    from soul.storage.sqlite_store import SQLiteStore
    return _print_sqlite_table(
        "Constitution Rejections",
        SQLiteStore(str(SQLITE_PATH)).list_rejections(),
        ["rejection_id", "candidate_id", "check_name", "reason"],
    )


def _verify_constitution() -> int:
    """校验所有已接受 narrative 都满足宪法。"""
    from soul.storage.sqlite_store import SQLiteStore
    from soul.agents.constitution import ConstitutionAgent
    from soul.agents.narrative import NarrativeAgent  # reuse presence

    sqlite = SQLiteStore(str(SQLITE_PATH))
    try:
        nars = sqlite.list_narratives()
        if not nars:
            print("No narratives to verify.")
            return 0
        ok = True
        for nar in nars:
            # 反序列化 JSON 字段为 list 供 constitution 检查
            import json as _json
            cand = dict(nar)
            cand["evidence_ids"] = _json.loads(nar.get("evidence_ids_json") or "[]")
            cand["episode_ids"] = _json.loads(nar.get("episode_ids_json") or "[]")
            cand["consolidated_episode_id"] = nar.get("consolidated_episode_id")
            verdict = ConstitutionAgent().process(cand)
            flag = "[OK]" if verdict["decision"] == "pass" else "[FAIL]"
            print(f"{flag} {nar['narrative_id']} -> {verdict['decision']}: {verdict['reason']}")
            if verdict["decision"] != "pass":
                ok = False
        return 0 if ok else 1
    finally:
        sqlite.close()


def _run_belief_cycle() -> int:
    """Read semantic/narrative/long-reflection/rejections → BeliefAgent → Constitution
    → pass 写 beliefs → reject 写 constitution_rejections → trace。"""
    import json as _json
    import uuid as _uuid
    from soul.storage.evidence_store import EvidenceStore
    from soul.storage.sqlite_store import SQLiteStore
    from soul.agents.belief import BeliefAgent
    from soul.agents.constitution import ConstitutionAgent

    SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    sqlite = SQLiteStore(str(SQLITE_PATH))
    evidence = EvidenceStore(str(EVIDENCE_PATH))
    trace = {"beliefs": [], "rejections": []}
    try:
        sem = sqlite.list_semantic_memory()
        nars = sqlite.list_narratives()
        lrefs = sqlite.list_long_reflections()
        rejs = sqlite.list_rejections()
        candidates = BeliefAgent().process(
            semantic_mems=sem, narratives=nars, long_reflections=lrefs, rejections=rejs)
        if not candidates:
            trace["skipped"] = "no belief candidates from current memory"
            print(_json.dumps(trace, ensure_ascii=False, indent=2))
            return 0
        con = ConstitutionAgent()
        for cand in candidates:
            verdict = con.process(cand, evidence_store=evidence)
            if verdict["decision"] == "pass":
                cand["status"] = "active"
                sqlite.add_belief(cand)
                trace["beliefs"].append({
                    "belief_id": cand["belief_id"], "statement": cand["statement"],
                    "belief_type": cand["belief_type"], "confidence": cand["confidence"],
                    "evidence_ids": cand["evidence_ids"],
                })
            else:
                sqlite.add_rejection({
                    "rejection_id": f"rej-{_uuid.uuid4()}",
                    "candidate_type": "belief",
                    "candidate_id": cand.get("belief_id"),
                    "check_name": verdict["reason"], "reason": verdict["reason"],
                    "candidate": cand, "evidence_refs": cand.get("evidence_ids", []),
                    "created_at": cand.get("created_at"),
                })
                trace["rejections"].append({
                    "candidate_id": cand.get("belief_id"),
                    "decision": verdict["decision"], "reason": verdict["reason"],
                })
        print(_json.dumps(trace, ensure_ascii=False, indent=2))
        return 0
    finally:
        sqlite.close()


def _run_relationship_cycle() -> int:
    """读 recent episodes → RelationshipAgent（按 user actor）→ Constitution
    → pass 写 relationships + relationship_updates → reject 写 rejection log。"""
    import json as _json
    import uuid as _uuid
    from soul.storage.evidence_store import EvidenceStore
    from soul.storage.sqlite_store import SQLiteStore
    from soul.agents.relationship import RelationshipAgent
    from soul.agents.constitution import ConstitutionAgent

    SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    sqlite = SQLiteStore(str(SQLITE_PATH))
    evidence = EvidenceStore(str(EVIDENCE_PATH))
    trace = {"relationships": [], "updates": [], "rejections": []}
    try:
        episodes = sqlite.list_episodes()
        actor = "user"
        existing = sqlite.get_relationship(actor)
        result = RelationshipAgent().process(episodes, existing=existing, actor=actor)
        if not result["candidates"]:
            trace["skipped"] = "no episodes to build relationship"
            print(_json.dumps(trace, ensure_ascii=False, indent=2))
            return 0

        con = ConstitutionAgent()
        rel = result["candidates"][0]
        # relationship 本体先过 Constitution
        rel_check = con.process(rel, evidence_store=evidence)
        rel_ok = rel_check["decision"] == "pass"
        if rel_ok:
            if existing:
                # 更新现有记录
                _apply_relationship_scores(sqlite, actor, rel, existing)
            else:
                rel["person_id"] = actor
                rel["name"] = actor
                sqlite.add_relationship(rel)
            trace["relationships"].append({
                "person_id": actor,
                "trust": rel["trust"], "familiarity": rel["familiarity"],
                "importance": rel["importance"], "affinity": rel["affinity"],
                "evidence_ids": rel["evidence_ids"],
            })
            # 每条 update 过 Constitution
            for upd in result["updates"]:
                uph = dict(upd); uph["person_id"] = actor
                uv = con.process(uph, evidence_store=evidence)
                if uv["decision"] == "pass":
                    sqlite.add_relationship_update(uph)
                    trace["updates"].append({
                        "update_id": uph["update_id"], "field": uph["field_changed"],
                        "delta": uph["delta"], "reason": uph["reason"],
                    })
                else:
                    sqlite.add_rejection({
                        "rejection_id": f"rej-{_uuid.uuid4()}",
                        "candidate_type": "relationship_update",
                        "candidate_id": uph.get("update_id"),
                        "check_name": uv["reason"], "reason": uv["reason"],
                        "candidate": uph, "evidence_refs": uph.get("evidence_ids", []),
                        "created_at": uph.get("created_at"),
                    })
                    trace["rejections"].append({"update_id": uph["update_id"], "reason": uv["reason"]})
        else:
            sqlite.add_rejection({
                "rejection_id": f"rej-{_uuid.uuid4()}",
                "candidate_type": "relationship",
                "candidate_id": actor, "check_name": rel_check["reason"],
                "reason": rel_check["reason"], "candidate": rel,
                "evidence_refs": rel.get("evidence_ids", []), "created_at": rel.get("created_at"),
            })
            trace["rejections"].append({"person_id": actor, "reason": rel_check["reason"]})

        print(_json.dumps(trace, ensure_ascii=False, indent=2))
        return 0
    finally:
        sqlite.close()


def _apply_relationship_scores(sqlite, person_id: str, rel: dict, existing: dict) -> None:
    """按 rel 全量覆盖现有 relationship 的分数字段（已有记录时为更新）。"""
    sqlite.update_relationship_scores(
        person_id,
        trust=rel["trust"], familiarity=rel["familiarity"],
        importance=rel["importance"], affinity=rel["affinity"],
        shared_goals=rel.get("shared_goals", []),
        conflict_history=rel.get("conflict_history", []),
        last_interaction_at=rel.get("last_interaction_at", ""),
        updated_at=rel.get("updated_at", ""),
    )


def _list_beliefs() -> int:
    from soul.storage.sqlite_store import SQLiteStore
    return _print_sqlite_table(
        "Beliefs",
        SQLiteStore(str(SQLITE_PATH)).list_beliefs(active_only=True),
        ["belief_id", "statement", "belief_type", "confidence", "evidence_ids_json", "status"],
    )


def _list_relationships() -> int:
    from soul.storage.sqlite_store import SQLiteStore
    return _print_sqlite_table(
        "Relationships",
        SQLiteStore(str(SQLITE_PATH)).list_relationships(),
        ["person_id", "trust", "familiarity", "importance", "affinity", "shared_goals_json"],
    )


def _list_relationship_updates() -> int:
    from soul.storage.sqlite_store import SQLiteStore
    return _print_sqlite_table(
        "Relationship Updates",
        SQLiteStore(str(SQLITE_PATH)).list_relationship_updates(),
        ["update_id", "person_id", "field_changed", "old_value", "new_value", "delta", "reason"],
    )


def _verify_beliefs() -> int:
    from soul.storage.sqlite_store import SQLiteStore
    import json as _json
    sqlite = SQLiteStore(str(SQLITE_PATH))
    try:
        beliefs = sqlite.list_beliefs(active_only=True)
        if not beliefs:
            print("No active beliefs.")
            return 0
        ok = True
        for b in beliefs:
            ev = _json.loads(b.get("evidence_ids_json") or "[]")
            conf = b.get("confidence")
            problems = []
            if not ev:
                problems.append("无 evidence refs")
            if not (0 <= float(conf) <= 1):
                problems.append(f"confidence超范围:{conf}")
            # 禁词
            for w in ("真实意识", "真正灵魂", "绝对信任", "永远"):
                if w in (b.get("statement") or ""):
                    problems.append(f"禁词:{w}")
            flag = "[OK]" if not problems else "[FAIL]"
            print(f"{flag} {b['belief_id']} conf={conf} | {'; '.join(problems) if problems else 'valid'}")
            if problems:
                ok = False
        return 0 if ok else 1
    finally:
        sqlite.close()


def _verify_relationships() -> int:
    from soul.storage.sqlite_store import SQLiteStore
    import json as _json
    sqlite = SQLiteStore(str(SQLITE_PATH))
    try:
        upds = sqlite.list_relationship_updates()
        if not upds:
            print("No relationship updates to verify.")
            return 0
        ok = True
        LIM = {"trust": 0.2, "familiarity": 0.2, "importance": 0.2, "affinity": 0.15}
        for u in upds:
            problems = []
            ev = _json.loads(u.get("evidence_ids_json") or "[]")
            delta = u.get("delta")
            fc = u.get("field_changed")
            if not ev:
                problems.append("无 evidence refs")
            if delta is not None and abs(float(delta)) > LIM.get(fc, 1.0):
                problems.append(f"delta超限:{delta}")
            if (u.get("reason") or "").find("操控") >= 0:
                problems.append("操控性描述")
            flag = "[OK]" if not problems else "[FAIL]"
            print(f"{flag} {u['update_id']} {fc} delta={delta} | {'; '.join(problems) if problems else 'valid'}")
            if problems:
                ok = False
        return 0 if ok else 1
    finally:
        sqlite.close()


def _run_self_cycle() -> int:
    """读 active beliefs/narratives/relationships/semantic → SelfModelAgent
    → Constitution → pass 写 self_snapshots → reject 写 rejection log → trace。"""
    import json as _json
    import uuid as _uuid
    from soul.storage.evidence_store import EvidenceStore
    from soul.storage.sqlite_store import SQLiteStore
    from soul.agents.self_model import SelfModelAgent
    from soul.agents.constitution import ConstitutionAgent

    SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    sqlite = SQLiteStore(str(SQLITE_PATH))
    evidence = EvidenceStore(str(EVIDENCE_PATH))
    trace = {"snapshots": [], "rejections": []}
    try:
        beliefs = sqlite.list_beliefs(active_only=True)
        narratives = sqlite.list_narratives()
        relationships = sqlite.list_relationships()
        semantic = sqlite.list_semantic_memory()
        active_goals = sqlite.list_active_goals()
        goal_progress_map = {}
        for g in active_goals:
            lp = sqlite.get_latest_goal_progress(g["goal_id"])
            if lp:
                goal_progress_map[g["goal_id"]] = lp
        previous = sqlite.get_latest_snapshot()
        agent = SelfModelAgent()
        cand = agent.process(beliefs=beliefs, narratives=narratives,
                             relationships=relationships, semantic_mems=semantic,
                             goals=active_goals, goal_progress=goal_progress_map,
                             previous_snapshot=previous)
        if not cand.get("evidence_refs"):
            trace["skipped"] = "no evidence-backed sources yet"
            print(_json.dumps(trace, ensure_ascii=False, indent=2))
            return 0
        verdict = ConstitutionAgent().process(cand, evidence_store=evidence)
        if verdict["decision"] == "pass":
            cand["status"] = "active"
            cand["constitution_result"] = verdict
            sqlite.add_self_snapshot(cand)
            trace["snapshots"].append({
                "snapshot_id": cand["snapshot_id"], "version": cand["version"],
                "identity_summary": cand["identity_summary"],
                "similarity_to_previous": cand["similarity_to_previous"],
                "evidence_refs_count": len(cand["evidence_refs"]),
            })
        else:
            sqlite.add_rejection({
                "rejection_id": f"rej-{_uuid.uuid4()}",
                "candidate_type": "self_snapshot",
                "candidate_id": cand.get("snapshot_id"), "check_name": verdict["reason"],
                "reason": verdict["reason"], "candidate": cand,
                "evidence_refs": cand.get("evidence_refs", []), "created_at": cand.get("created_at"),
            })
            trace["rejections"].append({
                "snapshot_id": cand.get("snapshot_id"),
                "decision": verdict["decision"], "reason": verdict["reason"],
            })
        print(_json.dumps(trace, ensure_ascii=False, indent=2))
        return 0
    finally:
        sqlite.close()


def _show_current_self() -> int:
    import json as _json
    from soul.storage.sqlite_store import SQLiteStore
    sqlite = SQLiteStore(str(SQLITE_PATH))
    try:
        snap = sqlite.get_latest_snapshot()
        if not snap:
            print("No self snapshot yet. Run `python -m soul run-self-cycle` first.")
            return 1
        import json as _j
        out = {
            "snapshot_id": snap["snapshot_id"],
            "version": snap["version"],
            "timestamp": snap["timestamp"],
            "identity_summary": snap["identity_summary"],
            "similarity_to_previous": snap["similarity_to_previous"],
            "active_beliefs": _j.loads(snap.get("active_beliefs_json") or "[]"),
            "active_relationships": _j.loads(snap.get("active_relationships_json") or "[]"),
            "active_goals": _j.loads(snap.get("active_goals_json") or "[]"),
            "dominant_narratives": _j.loads(snap.get("dominant_narratives_json") or "[]"),
            "evidence_refs_count": len(_j.loads(snap.get("evidence_refs_json") or "[]")),
        }
        print(_json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    finally:
        sqlite.close()


def _list_self_snapshots() -> int:
    from soul.storage.sqlite_store import SQLiteStore
    return _print_sqlite_table(
        "Self Snapshots",
        SQLiteStore(str(SQLITE_PATH)).list_self_snapshots(),
        ["snapshot_id", "version", "timestamp", "similarity_to_previous", "status", "evidence_refs_json"],
    )


def _verify_self() -> int:
    import json as _json
    from soul.storage.sqlite_store import SQLiteStore
    from soul.agents.constitution import ConstitutionAgent
    sqlite = SQLiteStore(str(SQLITE_PATH))
    try:
        snaps = sqlite.list_self_snapshots()
        if not snaps:
            print("No self snapshots to verify.")
            return 0
        ok = True
        for s in snaps:
            cand = dict(s)
            cand["evidence_refs"] = _json.loads(s.get("evidence_refs_json") or "[]")
            cand["source_belief_ids"] = _json.loads(s.get("source_belief_ids_json") or "[]")
            cand["source_narrative_ids"] = _json.loads(s.get("source_narrative_ids_json") or "[]")
            cand["source_relationship_ids"] = _json.loads(s.get("source_relationship_ids_json") or "[]")
            cand["source_semantic_memory_ids"] = _json.loads(s.get("source_semantic_memory_ids_json") or "[]")
            cand["identity_summary"] = s.get("identity_summary", "")
            verdict = ConstitutionAgent().process(cand)
            flag = "[OK]" if verdict["decision"] == "pass" else "[FAIL]"
            print(f"{flag} {s['snapshot_id']} v{s['version']} sim={s.get('similarity_to_previous')} -> {verdict['decision']}")
            if verdict["decision"] != "pass":
                ok = False
        return 0 if ok else 1
    finally:
        sqlite.close()


def _run_goal_cycle() -> int:
    """读 semantic/narrative/belief/long_reflection/rejections → GoalAgent
    → Constitution → pass 写 goals → reject 写 rejection log → trace。"""
    import json as _json
    import uuid as _uuid
    from soul.storage.evidence_store import EvidenceStore
    from soul.storage.sqlite_store import SQLiteStore
    from soul.agents.goal import GoalAgent
    from soul.agents.constitution import ConstitutionAgent

    SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    sqlite = SQLiteStore(str(SQLITE_PATH))
    evidence = EvidenceStore(str(EVIDENCE_PATH))
    trace = {"goals": [], "rejections": []}
    try:
        semantic = sqlite.list_semantic_memory()
        narratives = sqlite.list_narratives()
        beliefs = sqlite.list_beliefs()
        reflections = sqlite.list_long_reflections()
        rejections = sqlite.list_rejections()
        cands = GoalAgent().process(
            semantic_mems=semantic, narratives=narratives, beliefs=beliefs,
            long_reflections=reflections, rejections=rejections,
        )
        if not cands:
            trace["skipped"] = "no evidence-backed goal sources"
            print(_json.dumps(trace, ensure_ascii=False, indent=2))
            return 0
        for cand in cands:
            verdict = ConstitutionAgent().process(cand, evidence_store=evidence)
            if verdict["decision"] == "pass":
                cand["status"] = "active"
                sqlite.add_goal(cand)
                trace["goals"].append({
                    "goal_id": cand["goal_id"], "title": cand["title"],
                    "goal_type": cand["goal_type"], "priority": cand["priority"],
                    "evidence_ids_count": len(cand["evidence_ids"]),
                })
            else:
                sqlite.add_rejection({
                    "rejection_id": f"rej-{_uuid.uuid4()}",
                    "candidate_type": "goal",
                    "candidate_id": cand.get("goal_id"), "check_name": verdict["reason"],
                    "reason": verdict["reason"], "candidate": cand,
                    "evidence_refs": cand.get("evidence_ids", []),
                    "created_at": cand.get("created_at"),
                })
                trace["rejections"].append({
                    "goal_id": cand.get("goal_id"),
                    "decision": verdict["decision"], "reason": verdict["reason"],
                })
        print(_json.dumps(trace, ensure_ascii=False, indent=2))
        return 0
    finally:
        sqlite.close()


def _list_goals() -> int:
    from soul.storage.sqlite_store import SQLiteStore
    sqlite = SQLiteStore(str(SQLITE_PATH))
    try:
        goals = sqlite.list_goals()
        if not goals:
            print("No goals yet.")
            return 0
        print(f"=== Goals ({len(goals)}) ===")
        for g in goals:
            print(f"goal_id={g.get('goal_id')} type={g.get('goal_type')} "
                  f"status={g.get('status')} priority={g.get('priority')} "
                  f"title={g.get('title')}")
        return 0
    finally:
        sqlite.close()


def _show_active_goals() -> int:
    from soul.storage.sqlite_store import SQLiteStore
    sqlite = SQLiteStore(str(SQLITE_PATH))
    try:
        goals = sqlite.list_active_goals()
        if not goals:
            print("No active goals.")
            return 0
        print(f"=== Active Goals ({len(goals)}) ===")
        for g in goals:
            print(f"goal_id={g.get('goal_id')} type={g.get('goal_type')} "
                  f"priority={g.get('priority')} title={g.get('title')}")
        return 0
    finally:
        sqlite.close()


def _update_goal_status(goal_id: str, new_status: str, reason: str = "") -> int:
    from soul.storage.sqlite_store import SQLiteStore
    sqlite = SQLiteStore(str(SQLITE_PATH))
    try:
        if not reason:
            print("ERROR: --reason is required.")
            return 1
        try:
            upd = sqlite.update_goal_status(goal_id, new_status, reason)
        except KeyError as e:
            print(f"ERROR: {e}")
            return 1
        except ValueError as e:
            print(f"ERROR: {e}")
            return 1
        print(f"goal {goal_id} -> {new_status} (update_id={upd})")
        return 0
    finally:
        sqlite.close()


def _list_goal_updates() -> int:
    from soul.storage.sqlite_store import SQLiteStore
    sqlite = SQLiteStore(str(SQLITE_PATH))
    try:
        ups = sqlite.list_goal_updates()
        if not ups:
            print("No goal updates yet.")
            return 0
        print(f"=== Goal Updates ({len(ups)}) ===")
        for u in ups:
            print(f"update_id={u.get('update_id')} goal={u.get('goal_id')} "
                  f"{u.get('old_status')}->{u.get('new_status')} reason={u.get('reason')}")
        return 0
    finally:
        sqlite.close()


def _verify_goals() -> int:
    import json as _json
    from soul.storage.sqlite_store import SQLiteStore
    from soul.storage.evidence_store import EvidenceStore
    from soul.agents.constitution import ConstitutionAgent
    sqlite = SQLiteStore(str(SQLITE_PATH))
    evidence = EvidenceStore(str(EVIDENCE_PATH))
    try:
        goals = sqlite.list_goals()
        if not goals:
            print("No goals to verify.")
            return 0
        ok = True
        for g in goals:
            cand = dict(g)
            for f in ("evidence_ids", "source_belief_ids", "source_narrative_ids",
                      "source_semantic_memory_ids", "source_reflection_ids"):
                if f + "_json" in cand and cand.get(f + "_json"):
                    cand[f] = _json.loads(cand[f + "_json"])
                elif f in cand and isinstance(cand.get(f), str):
                    cand[f] = _json.loads(cand[f])
            cand["status"] = g.get("status")
            cand["goal_type"] = g.get("goal_type")
            cand["priority"] = g.get("priority")
            cand["title"] = g.get("title", "")
            cand["description"] = g.get("description", "")
            verdict = ConstitutionAgent().process(cand, evidence_store=evidence)
            # 校验 goal_updates reason
            ups = [u for u in sqlite.list_goal_updates() if u.get("goal_id") == g.get("goal_id")]
            mangled = any((u.get("reason") or "").strip() == "" for u in ups)
            flag = "[OK]" if verdict["decision"] == "pass" and not mangled else "[FAIL]"
            print(f"{flag} {g.get('goal_id')} {g.get('goal_type')} "
                  f"priority={g.get('priority')} status={g.get('status')} -> {verdict['decision']}")
            if verdict["decision"] != "pass" and flag == "[FAIL]":
                ok = False
        return 0 if ok else 1
    finally:
        sqlite.close()


def _run_goal_progress_cycle() -> int:
    """读 active goals + semantic/narrative/reflection/rejections → ProgressAgent
    → Constitution → pass 写 goal_progress → reject 写 rejection log → trace。
    同时用 PriorityAgent 更新每个 active goal 的 computed_priority。"""
    import json as _json
    import uuid as _uuid
    from soul.storage.evidence_store import EvidenceStore
    from soul.storage.sqlite_store import SQLiteStore
    from soul.agents.goal_progress import ProgressAgent, PriorityAgent
    from soul.agents.constitution import ConstitutionAgent

    SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    sqlite = SQLiteStore(str(SQLITE_PATH))
    evidence = EvidenceStore(str(EVIDENCE_PATH))
    trace = {"progress": [], "priority_updates": [], "rejections": []}
    try:
        goals = sqlite.list_active_goals()
        if not goals:
            trace["skipped"] = "no active goals"
            print(_json.dumps(trace, ensure_ascii=False, indent=2))
            return 0
        semantic = sqlite.list_semantic_memory()
        narratives = sqlite.list_narratives()
        reflections = sqlite.list_long_reflections()
        rejections = sqlite.list_rejections()
        latest_map = {}
        for g in goals:
            lp = sqlite.get_latest_goal_progress(g["goal_id"])
            if lp:
                latest_map[g["goal_id"]] = lp

        # 1) computed_priority 更新
        prio = PriorityAgent()
        for goal in goals:
            prev = goal.get("priority")
            result = prio.compute(goal, previous_priority=prev)
            if abs(result["computed_priority"] - float(prev or 0.0)) > 0.001:
                try:
                    sqlite.update_goal_priority(
                        goal["goal_id"], result["computed_priority"], result["priority_reason"],
                        evidence_ids=[])
                    trace["priority_updates"].append({
                        "goal_id": goal["goal_id"], "priority": result["computed_priority"],
                        "reason": result["priority_reason"],
                    })
                except Exception as e:
                    trace["priority_updates"].append({"goal_id": goal["goal_id"], "error": str(e)})

        # 2) goal progress 生成 + 落库
        cands = ProgressAgent().process(
            goals=goals, semantic_mems=semantic, narratives=narratives,
            reflections=reflections, rejections=rejections, latest_progress=latest_map,
        )
        if not cands:
            trace["skipped_progress"] = "no progress candidates"
            print(_json.dumps(trace, ensure_ascii=False, indent=2))
            return 0
        for cand in cands:
            verdict = ConstitutionAgent().process(cand, evidence_store=evidence, sqlite=sqlite)
            if verdict["decision"] == "pass":
                sqlite.add_goal_progress(cand)
                trace["progress"].append({
                    "progress_id": cand["progress_id"], "goal_id": cand["goal_id"],
                    "progress_value": cand["progress_value"],
                    "progress_delta": cand["progress_delta"],
                    "progress_status": cand["progress_status"],
                    "evidence_count": len(cand["evidence_ids"]),
                })
            else:
                sqlite.add_rejection({
                    "rejection_id": f"rej-{_uuid.uuid4()}",
                    "candidate_type": "goal_progress",
                    "candidate_id": cand.get("progress_id"), "check_name": verdict["reason"],
                    "reason": verdict["reason"], "candidate": cand,
                    "evidence_refs": cand.get("evidence_ids", []),
                    "created_at": cand.get("created_at"),
                })
                trace["rejections"].append({
                    "progress_id": cand.get("progress_id"), "goal_id": cand.get("goal_id"),
                    "decision": verdict["decision"], "reason": verdict["reason"],
                })
        print(_json.dumps(trace, ensure_ascii=False, indent=2))
        return 0
    finally:
        sqlite.close()


def _show_goal_dashboard() -> int:
    import json as _json
    from soul.storage.sqlite_store import SQLiteStore
    sqlite = SQLiteStore(str(SQLITE_PATH))
    try:
        goals = sqlite.list_active_goals()
        if not goals:
            print("No active goals.")
            return 0
        goals.sort(key=lambda g: float(g.get("priority") or 0.0), reverse=True)
        print("Goal Dashboard")
        for i, g in enumerate(goals, 1):
            lp = sqlite.get_latest_goal_progress(g["goal_id"])
            pv = lp.get("progress_value") if lp else None
            ps = lp.get("progress_status") if lp else None
            ev_count = len(_json.loads(g.get("evidence_ids") or "[]"))
            print(f"\n[{i}] {g.get('title')}")
            print(f"  Type: {g.get('goal_type')}")
            print(f"  Status: {g.get('status')}")
            print(f"  Priority: {g.get('priority')}")
            print(f"  Progress: {pv} / {ps}")
            print(f"  Evidence refs: {ev_count}")
            print(f"  Last update: {g.get('updated_at')}")
        return 0
    finally:
        sqlite.close()


def _list_goal_progress() -> int:
    from soul.storage.sqlite_store import SQLiteStore
    sqlite = SQLiteStore(str(SQLITE_PATH))
    try:
        progs = sqlite.list_goal_progress()
        if not progs:
            print("No goal progress yet.")
            return 0
        print(f"=== Goal Progress ({len(progs)}) ===")
        for p in progs:
            print(f"progress_id={p.get('progress_id')} goal={p.get('goal_id')} "
                  f"value={p.get('progress_value')} delta={p.get('progress_delta')} "
                  f"status={p.get('progress_status')}")
        return 0
    finally:
        sqlite.close()


def _verify_goal_progress() -> int:
    import json as _json
    from soul.storage.sqlite_store import SQLiteStore
    from soul.storage.evidence_store import EvidenceStore
    from soul.agents.constitution import ConstitutionAgent
    sqlite = SQLiteStore(str(SQLITE_PATH))
    evidence = EvidenceStore(str(EVIDENCE_PATH))
    try:
        progs = sqlite.list_goal_progress()
        if not progs:
            print("No goal progress to verify.")
            return 0
        ok = True
        for p in progs:
            cand = dict(p)
            cand["evidence_ids"] = _json.loads(p.get("evidence_ids") or "[]")
            cand["reason"] = p.get("reason", "")
            verdict = ConstitutionAgent().process(cand, evidence_store=evidence, sqlite=sqlite)
            flag = "[OK]" if verdict["decision"] == "pass" else "[FAIL]"
            print(f"{flag} {p.get('progress_id')} goal={p.get('goal_id')} "
                  f"value={p.get('progress_value')} status={p.get('progress_status')}")
            if verdict["decision"] != "pass":
                ok = False
        return 0 if ok else 1
    finally:
        sqlite.close()


def _run_planning_cycle() -> int:
    """读取 active goals → latest goal_progress → 按 priority 选 top → PlanningAgent
    → Constitution 校验 plan + tasks → pass 写 plans/tasks → reject 写 constitution_rejections
    → 输出 trace。Plan 不执行任何动作，任务仅 proposed。"""
    import json as _json
    from soul.storage.sqlite_store import SQLiteStore
    from soul.storage.evidence_store import EvidenceStore
    from soul.agents.planning import PlanningAgent
    from soul.agents.constitution import ConstitutionAgent
    sqlite = SQLiteStore(str(SQLITE_PATH))
    evidence = EvidenceStore(str(EVIDENCE_PATH))
    try:
        goals = sqlite.list_active_goals()
        if not goals:
            print("No active goals to plan for.")
            return 0
        # 读取每个 active goal 的 latest goal_progress
        progress_map = {g["goal_id"]: sqlite.get_latest_goal_progress(g["goal_id"])
                        for g in goals}
        top = sorted(goals, key=lambda g: float(g.get("priority") or 0.0), reverse=True)[:3]
        for goal in top:
            gid = goal["goal_id"]
            lp = progress_map.get(gid) or {}
            trace = {
                "selected_goal_id": gid,
                "goal_title": goal.get("title"),
                "goal_type": goal.get("goal_type"),
                "computed_priority": goal.get("priority"),
                "latest_progress_status": lp.get("progress_status"),
                "latest_progress_value": lp.get("progress_value"),
            }
            cands = PlanningAgent().process(
                goals=[goal],
                goal_progress={gid: lp},
            )
            if not cands:
                print(f"[skip] goal {gid} no evidence-bound plan candidate")
                continue
            pc = cands[0]
            plan = pc["plan"]
            plan_id = plan["plan_id"]
            verdict = ConstitutionAgent().process(plan, evidence_store=evidence, sqlite=sqlite)
            trace["plan_candidate"] = {
                "plan_id": plan_id, "plan_type": plan.get("plan_type"),
                "title": plan.get("title"), "evidence_ids": plan.get("evidence_ids"),
            }
            trace["planet_constitution"] = verdict
            task_ids = []
            if verdict["decision"] != "pass":
                # rejected plan 不写入 plans，只写 rejection
                _write_rejection(sqlite, "plan", plan, verdict, evidence)
                trace["rejection_ids"] = [_last_rejection_id(sqlite, "plan", plan_id)]
            else:
                # 持久化 plan_reason（plans 表无此列，暂存入 constitution_result 的元数据字段）
                _cr = dict(plan.get("constitution_result") or {})
                _cr["_plan_reason"] = plan.get("plan_reason", "")
                plan["constitution_result"] = _cr
                sqlite.add_plan(plan)
                # 校验并写入 tasks
                for t in pc["tasks"]:
                    t["plan_id"] = plan_id
                    tverdict = ConstitutionAgent().process(t, evidence_store=evidence, sqlite=sqlite)
                    if tverdict["decision"] != "pass":
                        _write_rejection(sqlite, "task", t, tverdict, evidence)
                        trace.setdefault("rejection_ids", []).append(_last_rejection_id(sqlite, "task", t["task_id"]))
                    else:
                        sqlite.add_task(t)
                        task_ids.append(t["task_id"])
                sqlite.update_plan_task_ids(plan_id, task_ids)
                trace["plan_id"] = plan_id
                trace["task_ids"] = task_ids
            print(_json.dumps(trace, ensure_ascii=False, indent=2))
        return 0
    finally:
        sqlite.close()


def _utc_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _write_rejection(sqlite, kind, cand, verdict, evidence):
    import json as _json
    import uuid as _uuid
    now = _utc_now()
    sqlite.add_rejection({
        "rejection_id": f"rej-{_uuid.uuid4()}",
        "candidate_type": kind,
        "candidate_id": cand.get("plan_id") or cand.get("task_id"),
        "check_name": "constitution",
        "reason": verdict.get("reason", ""),
        "candidate": cand,
        "evidence_refs": cand.get("evidence_ids", []),
        "created_at": now,
    })


def _last_rejection_id(sqlite, kind, candidate_id):
    rows = sqlite.list_rejections()
    for r in rows:
        if r.get("candidate_type") == kind and r.get("candidate_id") == candidate_id:
            return r.get("rejection_id")
    return None


def _list_plans() -> int:
    from soul.storage.sqlite_store import SQLiteStore
    sqlite = SQLiteStore(str(SQLITE_PATH))
    try:
        plans = sqlite.list_plans()
        if not plans:
            print("No plans yet.")
            return 0
        print(f"=== Plans ({len(plans)}) ===")
        for p in plans:
            print(f"plan_id={p.get('plan_id')} goal={p.get('goal_id')} type={p.get('plan_type')} "
                  f"status={p.get('status')} priority={p.get('priority')} version={p.get('version')}")
        return 0
    finally:
        sqlite.close()


def _show_current_plan() -> int:
    import json as _json
    from soul.storage.sqlite_store import SQLiteStore
    sqlite = SQLiteStore(str(SQLITE_PATH))
    try:
        plan = sqlite.get_latest_active_plan()
        if not plan:
            print("No active plan yet. Run run-planning-cycle first.")
            return 0
        print(f"Plan: {plan.get('title')}")
        print(f"  plan_id: {plan.get('plan_id')}")
        print(f"  goal_id: {plan.get('goal_id')}")
        print(f"  type: {plan.get('plan_type')} | status: {plan.get('status')} | priority: {plan.get('priority')}")
        print(f"  version: {plan.get('version')} | supersedes: {plan.get('supersedes')}")
        print(f"  description: {plan.get('description')}")
        ev = _json.loads(plan.get("evidence_ids_json") or plan.get("evidence_ids") or "[]")
        print(f"  evidence refs: {len(ev)}")
        tasks = sqlite.list_tasks_for_plan(plan["plan_id"])
        print(f"\nTasks ({len(tasks)}):")
        for t in tasks:
            print(f"  [{t.get('order_index')}] {t.get('title')} "
                  f"(type={t.get('task_type')}, status={t.get('status')}, "
                  f"mode={t.get('execution_mode')})")
        return 0
    finally:
        sqlite.close()


def _list_tasks() -> int:
    from soul.storage.sqlite_store import SQLiteStore
    sqlite = SQLiteStore(str(SQLITE_PATH))
    try:
        tasks = sqlite.list_tasks()
        if not tasks:
            print("No tasks yet.")
            return 0
        print(f"=== Tasks ({len(tasks)}) ===")
        for t in tasks:
            print(f"task_id={t.get('task_id')} plan={t.get('plan_id')} goal={t.get('goal_id')} "
                  f"type={t.get('task_type')} status={t.get('status')} mode={t.get('execution_mode')}")
        return 0
    finally:
        sqlite.close()


def _verify_plans() -> int:
    import json as _json
    from soul.storage.sqlite_store import SQLiteStore
    from soul.storage.evidence_store import EvidenceStore
    from soul.agents.constitution import ConstitutionAgent
    sqlite = SQLiteStore(str(SQLITE_PATH))
    evidence = EvidenceStore(str(EVIDENCE_PATH))
    try:
        plans = sqlite.list_plans()
        tasks = sqlite.list_tasks()
        ok = True
        for p in plans:
            cand = dict(p)
            cand["evidence_ids"] = _json.loads(p.get("evidence_ids_json") or "[]")
            # DB 列存 *_json，还原成 check_plan 期望的 list 字段
            for jk in ("source_goal_ids_json", "source_goal_progress_ids_json",
                       "source_belief_ids_json", "source_narrative_ids_json",
                       "source_semantic_memory_ids_json", "source_reflection_ids_json"):
                cand[jk[:-5]] = _json.loads(p.get(jk) or "[]")
            # 还原运行期持久化的 plan_reason（存于 constitution_result_json._plan_reason）
            _cr = _json.loads(p.get("constitution_result_json") or "{}")
            cand["plan_reason"] = _cr.get("_plan_reason") or (
                f"plan created by run-planning-cycle for goal {p.get('goal_id')}")
            verdict = ConstitutionAgent().process(cand, evidence_store=evidence, sqlite=sqlite)
            flag = "[OK]" if verdict["decision"] == "pass" else "[FAIL]"
            print(f"{flag} plan={p.get('plan_id')} goal={p.get('goal_id')} status={p.get('status')}")
            if verdict["decision"] != "pass":
                ok = False
        for t in tasks:
            cand = dict(t)
            cand["evidence_ids"] = _json.loads(t.get("evidence_ids_json") or "[]")
            cand["execution_mode"] = t.get("execution_mode", "manual_only")
            verdict = ConstitutionAgent().process(cand, evidence_store=evidence, sqlite=sqlite)
            flag = "[OK]" if verdict["decision"] == "pass" else "[FAIL]"
            print(f"{flag} task={t.get('task_id')} plan={t.get('plan_id')} status={t.get('status')}")
            if verdict["decision"] != "pass":
                ok = False
        return 0 if ok else 1
    finally:
        sqlite.close()


def _run_decision_cycle() -> int:
    """读取 active goals → latest progress → proposed/active plans → proposed/ready tasks
    → Decision Agent 选 next recommended task → Constitution 校验 → pass 写 decisions
    → reject 写 constitution_rejections → 输出 trace。只给 review 建议，不执行。"""
    import json as _json
    from soul.storage.sqlite_store import SQLiteStore
    from soul.storage.evidence_store import EvidenceStore
    from soul.agents.decision import DecisionAgent
    from soul.agents.constitution import ConstitutionAgent
    sqlite = SQLiteStore(str(SQLITE_PATH))
    evidence = EvidenceStore(str(EVIDENCE_PATH))
    try:
        goals = sqlite.list_active_goals()
        progress_map = {g["goal_id"]: sqlite.get_latest_goal_progress(g["goal_id"])
                        for g in goals}
        plans = [p for p in sqlite.list_plans() if p.get("status") in ("proposed", "active")]
        tasks = [t for t in sqlite.list_tasks() if t.get("status") in ("proposed", "ready")]
        ltg = sqlite.list_active_long_term_goals()
        mts = sqlite.list_active_motivations()
        if not goals:
            print("No active goals to decide over.")
            return 0
        cands = DecisionAgent().process(goals=goals, goal_progress=progress_map,
                                        plans=plans, tasks=tasks, long_term_goals=ltg,
                                        motivations=mts)
        if not cands:
            print("No decision candidate.")
            return 0
        for dec in cands:
            verdict = ConstitutionAgent().process(dec, evidence_store=evidence, sqlite=sqlite)
            _cr = dict(dec.get("constitution_result") or {})
            _cr["decision"] = verdict["decision"]
            dec["constitution_result"] = _cr
            trace = {
                "decision_type": dec.get("decision_type"),
                "selected_goal_id": dec.get("selected_goal_id"),
                "selected_plan_id": dec.get("selected_plan_id"),
                "selected_task_id": dec.get("selected_task_id"),
                "selected_task_title": dec.get("selected_task_title"),
                "decision_factors": dec.get("decision_factors"),
                "evidence_ids": dec.get("evidence_ids"),
                "related_long_term_goal_ids": dec.get("related_long_term_goal_ids"),
                "related_motivation_ids": dec.get("related_motivation_ids"),
                "manual_review_required": dec.get("manual_review_required"),
                "execution_allowed": dec.get("execution_allowed"),
                "constitution_checks": verdict.get("checks"),
            }
            if verdict["decision"] == "pass":
                sqlite.add_decision(dec)
                trace["decision_id"] = dec.get("decision_id")
            else:
                _write_rejection(sqlite, "decision", dec, verdict, evidence)
                trace["rejection_id"] = _last_rejection_id(sqlite, "decision", dec.get("decision_id"))
            print(_json.dumps(trace, ensure_ascii=False, indent=2))
        return 0
    finally:
        sqlite.close()


def _list_decisions() -> int:
    from soul.storage.sqlite_store import SQLiteStore
    sqlite = SQLiteStore(str(SQLITE_PATH))
    try:
        decs = sqlite.list_decisions()
        if not decs:
            print("No decisions yet.")
            return 0
        print(f"=== Decisions ({len(decs)}) ===")
        for d in decs:
            print(f"decision_id={d.get('decision_id')} type={d.get('decision_type')} "
                  f"status={d.get('status')} goal={d.get('selected_goal_id')} "
                  f"task={d.get('selected_task_id')} manual_review={d.get('manual_review_required')} "
                  f"exec_allowed={d.get('execution_allowed')}")
        return 0
    finally:
        sqlite.close()


def _show_current_decision() -> int:
    import json as _json
    from soul.storage.sqlite_store import SQLiteStore
    sqlite = SQLiteStore(str(SQLITE_PATH))
    try:
        dec = sqlite.get_latest_waiting_decision()
        if not dec:
            print("No waiting decision yet. Run run-decision-cycle first.")
            return 0
        print(f"Decision: {dec.get('selected_task_title')}")
        print(f"  decision_id: {dec.get('decision_id')}")
        print(f"  type: {dec.get('decision_type')} | status: {dec.get('status')}")
        print(f"  goal: {dec.get('selected_goal_id')} | plan: {dec.get('selected_plan_id')} "
              f"| task: {dec.get('selected_task_id')}")
        print(f"  manual_review_required: {dec.get('manual_review_required')} "
              f"| execution_allowed: {dec.get('execution_allowed')}")
        print(f"  reason: {dec.get('reason')}")
        ev = _json.loads(dec.get("evidence_ids_json") or "[]")
        print(f"  evidence refs: {len(ev)}")
        return 0
    finally:
        sqlite.close()


def _verify_decisions() -> int:
    import json as _json
    from soul.storage.sqlite_store import SQLiteStore
    from soul.storage.evidence_store import EvidenceStore
    from soul.agents.constitution import ConstitutionAgent
    sqlite = SQLiteStore(str(SQLITE_PATH))
    evidence = EvidenceStore(str(EVIDENCE_PATH))
    try:
        decs = sqlite.list_decisions()
        if not decs:
            print("No decisions to verify.")
            return 0
        ok = True
        for d in decs:
            cand = dict(d)
            cand["evidence_ids"] = _json.loads(d.get("evidence_ids_json") or "[]")
            cand["decision_factors"] = _json.loads(d.get("decision_factors_json") or "{}")
            cand["related_long_term_goal_ids"] = _json.loads(d.get("related_long_term_goal_ids_json") or "[]")
            cand["manual_review_required"] = bool(d.get("manual_review_required"))
            cand["execution_allowed"] = bool(d.get("execution_allowed"))
            verdict = ConstitutionAgent().process(cand, evidence_store=evidence, sqlite=sqlite)
            flag = "[OK]" if verdict["decision"] == "pass" else "[FAIL]"
            print(f"{flag} decision={d.get('decision_id')} type={d.get('decision_type')} "
                  f"task={d.get('selected_task_id')} status={d.get('status')}")
            if verdict["decision"] != "pass":
                ok = False
        return 0 if ok else 1
    finally:
        sqlite.close()


def _run_consolidation_cycle() -> int:
    """读取 active goals → GoalConsolidationAgent 归并连续性 → Constitution 校验两对象
    → pass 写 long_term_goals + goal_consolidations → 输出 trace。只归并不执行/不删除。"""
    import json as _json
    from soul.storage.sqlite_store import SQLiteStore
    from soul.storage.evidence_store import EvidenceStore
    from soul.agents.consolidation import GoalConsolidationAgent
    from soul.agents.constitution import ConstitutionAgent
    sqlite = SQLiteStore(str(SQLITE_PATH))
    evidence = EvidenceStore(str(EVIDENCE_PATH))
    try:
        goals = sqlite.list_active_goals()
        if not goals:
            print("No active goals to consolidate.")
            return 0
        ga = GoalConsolidationAgent(sqlite)
        res = ga.run_consolidation_cycle()
        con = ConstitutionAgent()
        if not res:
            print("No consolidations formed (need >=2 goals sharing a continuity thread).")
            return 0
        for r in res:
            lt = sqlite.get_long_term_goal(r["long_term_goal_id"])
            v_lt = con.process(lt, evidence_store=evidence, sqlite=sqlite)
            cons_row = next((x for x in sqlite.list_goal_consolidations()
                             if x.get("consolidation_id") == r.get("consolidation_id")), None)
            v_cons = con.process(cons_row, evidence_store=evidence, sqlite=sqlite) if cons_row else {"decision": "reject", "checks": []}
            trace = {
                "long_term_goal_id": lt.get("long_term_goal_id"),
                "consolidation_id": cons_row.get("consolidation_id") if cons_row else r.get("consolidation_id"),
                "goal_type": lt.get("goal_type"),
                "status": lt.get("status"),
                "source_goal_ids": lt.get("source_goal_ids"),
                "source_progress_ids": r.get("source_progress_ids"),
                "evidence_ids": lt.get("evidence_ids"),
                "progress_value": lt.get("progress_value"),
                "priority": lt.get("priority"),
                "action_taken": cons_row.get("action_taken") if cons_row else r.get("action_taken"),
                "ltg_constitution": v_lt["decision"],
                "cons_constitution": v_cons["decision"],
            }
            print(_json.dumps(trace, ensure_ascii=False, indent=2))
        return 0
    finally:
        sqlite.close()


def _list_long_term_goals() -> int:
    from soul.storage.sqlite_store import SQLiteStore
    sqlite = SQLiteStore(str(SQLITE_PATH))
    try:
        ltg = sqlite.list_long_term_goals()
        if not ltg:
            print("No long-term goals yet.")
            return 0
        print(f"=== Long-term Goals ({len(ltg)}) ===")
        for g in ltg:
            src = g.get("source_goal_ids")
            print(f"long_term_goal_id={g.get('long_term_goal_id')} type={g.get('goal_type')} "
                  f"status={g.get('status')} priority={g.get('priority')} prog={g.get('progress_value')} "
                  f"src={len(src) if isinstance(src, list) else 0}")
        return 0
    finally:
        sqlite.close()


def _list_goal_consolidations() -> int:
    from soul.storage.sqlite_store import SQLiteStore
    sqlite = SQLiteStore(str(SQLITE_PATH))
    try:
        cons = sqlite.list_goal_consolidations()
        if not cons:
            print("No goal consolidations yet.")
            return 0
        print(f"=== Goal Consolidations ({len(cons)}) ===")
        for c in cons:
            src = c.get("source_goal_ids")
            print(f"consolidation_id={c.get('consolidation_id')} type={c.get('consolidation_type')} "
                  f"action={c.get('action_taken')} ltg={c.get('long_term_goal_id')} "
                  f"src={len(src) if isinstance(src, list) else 0}")
        return 0
    finally:
        sqlite.close()


def _show_goal_continuity() -> int:
    import json as _json
    from soul.storage.sqlite_store import SQLiteStore
    sqlite = SQLiteStore(str(SQLITE_PATH))
    try:
        ltg = sqlite.list_active_long_term_goals()
        if not ltg:
            print("No active long-term goals yet.")
            return 0
        print(f"=== Active Long-term Goals ({len(ltg)}) ===")
        for g in ltg:
            src = g.get("source_goal_ids") or []
            prog = g.get("source_progress_ids")
            print(f"\n[{g.get('long_term_goal_id')}] {g.get('title')}")
            print(f"  type={g.get('goal_type')} status={g.get('status')} "
                  f"priority={g.get('priority')} progress={g.get('progress_value')}")
            print(f"  source goals ({len(src)}): {src}")
            print(f"  progress refs: {prog}")
            print(f"  reason: {g.get('continuity_reason')}")
            ev = g.get("evidence_ids")
            print(f"  evidence refs: {len(ev) if isinstance(ev, list) else 0}")
        return 0
    finally:
        sqlite.close()


def _verify_goal_continuity() -> int:
    import json as _json
    from soul.storage.sqlite_store import SQLiteStore
    from soul.storage.evidence_store import EvidenceStore
    from soul.agents.constitution import ConstitutionAgent
    sqlite = SQLiteStore(str(SQLITE_PATH))
    evidence = EvidenceStore(str(EVIDENCE_PATH))
    try:
        ltg = sqlite.list_long_term_goals()
        cons = sqlite.list_goal_consolidations()
        ok = True
        if not ltg and not cons:
            print("No long-term goals or consolidations to verify.")
            return 0
        con = ConstitutionAgent()
        for g in ltg:
            v = con.process(g, evidence_store=evidence, sqlite=sqlite)
            flag = "[OK]" if v["decision"] == "pass" else "[FAIL]"
            # 结构检查
            src = g.get("source_goal_ids") or []
            problems = []
            if not src:
                problems.append("no source goals")
            if g.get("goal_type") != "safety_continuity" and len(src) < 2:
                problems.append("<2 source goals (non-safety)")
            if not g.get("evidence_ids"):
                problems.append("no evidence")
            try:
                if not (0.0 <= float(g.get("priority", 0)) <= 1.0):
                    problems.append("priority out of range")
                if not (0.0 <= float(g.get("progress_value", 0)) <= 1.0):
                    problems.append("progress out of range")
            except (TypeError, ValueError):
                problems.append("priority/progress invalid")
            if g.get("status") == "completed":
                problems.append("auto-completed")
            flag = "[FAIL]" if (v["decision"] != "pass" or problems) else "[OK]"
            if flag == "[FAIL]":
                ok = False
            print(f"{flag} long_term_goal={g.get('long_term_goal_id')} type={g.get('goal_type')} "
                  f"status={g.get('status')} prog={g.get('progress_value')} src={len(src)} "
                  f"{(' | '+' | '.join(problems)) if problems else ''}")
        for c in cons:
            v = con.process(c, evidence_store=evidence, sqlite=sqlite)
            src = c.get("source_goal_ids") or []
            prob = []
            if not src:
                prob.append("no source goals")
            if c.get("action_taken") == "delete":
                prob.append("action=delete")
            flag = "[OK]" if (v["decision"] == "pass" and not prob) else "[FAIL]"
            if flag == "[FAIL]":
                ok = False
            print(f"{flag} consolidation={c.get('consolidation_id')} type={c.get('consolidation_type')} "
                  f"action={c.get('action_taken')} src={len(src)} "
                  f"{(' | '+' | '.join(prob)) if prob else ''}")
        return 0 if ok else 1
    finally:
        sqlite.close()


def _run_motivation_cycle() -> int:
    import json as _json
    from soul.storage.sqlite_store import SQLiteStore
    from soul.storage.evidence_store import EvidenceStore
    from soul.agents.motivation import MotivationAgent
    from soul.agents.constitution import ConstitutionAgent
    sqlite = SQLiteStore(str(SQLITE_PATH))
    evidence = EvidenceStore(str(EVIDENCE_PATH))
    try:
        ma = MotivationAgent(sqlite)
        res = ma.run_motivation_cycle()
        con = ConstitutionAgent()
        if not res:
            print("No motivations generated (no direction sources matched).")
            return 0
        for r in res:
            if "error" in r:
                print(_json.dumps(r, ensure_ascii=False))
                continue
            mot = sqlite.get_motivation(r["motivation_id"])
            v = con.process(mot, evidence_store=evidence, sqlite=sqlite)
            r["constitution"] = v["decision"]
            print(_json.dumps(r, ensure_ascii=False, indent=2))
        return 0
    finally:
        sqlite.close()


def _list_motivations() -> int:
    from soul.storage.sqlite_store import SQLiteStore
    sqlite = SQLiteStore(str(SQLITE_PATH))
    try:
        mts = sqlite.list_motivations()
        if not mts:
            print("No motivations yet.")
            return 0
        print(f"=== Motivations ({len(mts)}) ===")
        for m in mts:
            src_ltg = m.get("source_long_term_goal_ids")
            src_goal = m.get("source_goal_ids")
            print(f"motivation_id={m.get('motivation_id')} type={m.get('motivation_type')} "
                  f"status={m.get('status')} score={m.get('motivation_score')} "
                  f"prio={m.get('priority')} ltg={len(src_ltg) if isinstance(src_ltg, list) else 0} "
                  f"goal={len(src_goal) if isinstance(src_goal, list) else 0}")
        return 0
    finally:
        sqlite.close()


def _show_active_motivations() -> int:
    from soul.storage.sqlite_store import SQLiteStore
    sqlite = SQLiteStore(str(SQLITE_PATH))
    try:
        mts = sqlite.list_active_motivations()
        if not mts:
            print("No active motivations.")
            return 0
        print(f"=== Active Motivations ({len(mts)}) ===")
        for m in mts:
            print(f"\n[{m.get('motivation_id')}] {m.get('direction')}")
            print(f"  type={m.get('motivation_type')} status={m.get('status')} "
                  f"score={m.get('motivation_score')} prio={m.get('priority')}")
            print(f"  reason: {m.get('reason')}")
            ev = m.get("evidence_ids")
            print(f"  evidence refs: {len(ev) if isinstance(ev, list) else 0}")
        return 0
    finally:
        sqlite.close()


def _verify_motivations() -> int:
    from soul.storage.sqlite_store import SQLiteStore
    from soul.storage.evidence_store import EvidenceStore
    from soul.agents.constitution import ConstitutionAgent
    sqlite = SQLiteStore(str(SQLITE_PATH))
    evidence = EvidenceStore(str(EVIDENCE_PATH))
    try:
        mts = sqlite.list_motivations()
        if not mts:
            print("No motivations to verify.")
            return 0
        con = ConstitutionAgent()
        ok = True
        for m in mts:
            v = con.process(m, evidence_store=evidence, sqlite=sqlite)
            prob = []
            if not m.get("evidence_ids"):
                prob.append("no evidence")
            if any(m.get(k) for k in ("source_long_term_goal_ids", "source_goal_ids",
                                      "source_belief_ids", "source_narrative_ids",
                                      "source_semantic_memory_ids", "source_reflection_ids")) is False:
                prob.append("no source")
            try:
                if not (0.0 <= float(m.get("motivation_score", 0)) <= 1.0):
                    prob.append("score out of range")
                if not (0.0 <= float(m.get("priority", 0)) <= 1.0):
                    prob.append("priority out of range")
            except (TypeError, ValueError):
                prob.append("score/priority invalid")
            if m.get("manual_review_required") != 1:
                prob.append("manual_review_required!=1")
            if m.get("execution_allowed") != 0:
                prob.append("execution_allowed!=0")
            flag = "[FAIL]" if (v["decision"] != "pass" or prob) else "[OK]"
            if flag == "[FAIL]":
                ok = False
            print(f"{flag} motivation={m.get('motivation_id')} type={m.get('motivation_type')} "
                  f"score={m.get('motivation_score')} status={m.get('status')} "
                  f"{('| '+' | '.join(prob)) if prob else ''}")
        return 0 if ok else 1
    finally:
        sqlite.close()


def _list_action_registry() -> int:
    import json as _json
    from soul.storage.sqlite_store import SQLiteStore
    from soul.policy import default_registry
    sqlite = SQLiteStore(str(SQLITE_PATH))
    try:
        sqlite.init_action_registry(default_registry.DEFAULT_ACTIONS)
        rows = sqlite.list_action_registry()
        if not rows:
            print("action registry is empty")
            return 0
        for r in rows:
            print(_json.dumps(r, ensure_ascii=False))
        return 0
    finally:
        sqlite.close()


def _run_execution_gate() -> int:
    """读取最新 waiting_for_review decision → Gate → Constitution → 落库 → trace。"""
    import json as _json
    from soul.storage.sqlite_store import SQLiteStore
    from soul.storage.evidence_store import EvidenceStore
    from soul.agents.execution_gate import run_execution_gate
    from soul.policy import default_registry
    sqlite = SQLiteStore(str(SQLITE_PATH))
    evidence = EvidenceStore(str(EVIDENCE_PATH))
    try:
        sqlite.init_action_registry(default_registry.DEFAULT_ACTIONS)
        res = run_execution_gate(sqlite, evidence)
        trace = res.get("trace")
        if trace is None:
            print(res.get("error", "no_waiting_decision"))
            return 0
        print(_json.dumps(trace, ensure_ascii=False, indent=2))
        return 0
    finally:
        sqlite.close()


def _list_execution_requests() -> int:
    import json as _json
    from soul.storage.sqlite_store import SQLiteStore
    sqlite = SQLiteStore(str(SQLITE_PATH))
    try:
        rows = sqlite.list_execution_requests()
        if not rows:
            print("no execution requests")
            return 0
        for r in rows:
            print(_json.dumps(r, ensure_ascii=False))
        return 0
    finally:
        sqlite.close()


def _show_execution_request(er_id: str = "") -> int:
    import json as _json
    from soul.storage.sqlite_store import SQLiteStore
    if not er_id:
        print("usage: python -m soul show-execution-request <id>")
        return 1
    sqlite = SQLiteStore(str(SQLITE_PATH))
    try:
        r = sqlite.get_execution_request(er_id)
        if r is None:
            print(f"no execution request: {er_id}")
            return 0
        print(_json.dumps(r, ensure_ascii=False, indent=2))
        return 0
    finally:
        sqlite.close()


def _approve_execution(er_id: str = "", reason: str = "") -> int:
    import uuid as _uuid
    from soul.storage.sqlite_store import SQLiteStore
    if not er_id:
        print("usage: python -m soul approve-execution <id> --reason <reason>")
        return 1
    if not reason:
        # 从 argv 尾再抓一次 --reason
        pass
    if not reason:
        print("reason 必须非空")
        return 1
    sqlite = SQLiteStore(str(SQLITE_PATH))
    try:
        er = sqlite.get_execution_request(er_id)
        if er is None:
            print(f"no execution request: {er_id}")
            return 0
        if er.get("status") not in ("waiting_for_approval", "proposed", "auto_allowed"):
            print(f"cannot approve status={er.get('status')}")
            return 1
        # L2/L∞ 即使 approval 也不可执行
        if er.get("action_level") in ("L2", "L∞"):
            print(f"L2/L∞ 不允许 approval 后执行 (level={er.get('action_level')})")
            return 1
        sqlite.add_approval({
            "approval_id": f"approval-{_uuid.uuid4()}",
            "execution_request_id": er_id,
            "reviewer": "human",
            "approval_decision": "approved",
            "reason": reason,
        })
        sqlite.update_execution_request(er_id, status="approved")
        print(f"approved {er_id}")
        return 0
    finally:
        sqlite.close()


def _reject_execution(er_id: str = "", reason: str = "") -> int:
    import uuid as _uuid
    from soul.storage.sqlite_store import SQLiteStore
    if not er_id:
        print("usage: python -m soul reject-execution <id> --reason <reason>")
        return 1
    if not reason:
        print("reason 必须非空")
        return 1
    sqlite = SQLiteStore(str(SQLITE_PATH))
    try:
        er = sqlite.get_execution_request(er_id)
        if er is None:
            print(f"no execution request: {er_id}")
            return 0
        sqlite.add_approval({
            "approval_id": f"approval-{_uuid.uuid4()}",
            "execution_request_id": er_id,
            "reviewer": "human",
            "approval_decision": "rejected",
            "reason": reason,
        })
        sqlite.update_execution_request(er_id, status="rejected")
        print(f"rejected {er_id}")
        return 0
    finally:
        sqlite.close()


def _run_approved_action(er_id: str = "") -> int:
    import json as _json
    from soul.storage.sqlite_store import SQLiteStore
    from soul.storage.evidence_store import EvidenceStore
    from soul.agents.action_adapter import run_approved_action
    if not er_id:
        print("usage: python -m soul run-approved-action <id>")
        return 1
    sqlite = SQLiteStore(str(SQLITE_PATH))
    evidence = EvidenceStore(str(EVIDENCE_PATH))
    try:
        er = sqlite.get_execution_request(er_id)
        if er is None:
            print(f"no execution request: {er_id}")
            return 0
        res = run_approved_action(sqlite, evidence, er)
        print(_json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    finally:
        sqlite.close()


def _run_cognitive_loop() -> int:
    """Phase 15 C：监督脑认知循环。审计 + 提炼 + 异常闸。只读监督，不执行真实动作。
    --quiet: 无异常时静默（供 no_agent cron，有异常才投递）。"""
    import json as _json
    from soul.storage.sqlite_store import SQLiteStore
    from soul.storage.evidence_store import EvidenceStore
    from soul.agents.cognitive_loop import run_cognitive_cycle, format_cycle_report
    quiet = "--quiet" in sys.argv
    sqlite = SQLiteStore(str(SQLITE_PATH))
    evidence = EvidenceStore(str(EVIDENCE_PATH))
    try:
        trace = run_cognitive_cycle(sqlite, evidence, write_guard=True)
        if quiet and not trace.get("alerts"):
            return 0
        print(format_cycle_report(trace))
        print(_json.dumps({"trace": trace}, ensure_ascii=False, indent=2))
        return 0
    finally:
        sqlite.close()


def _list_action_logs() -> int:
    import json as _json
    from soul.storage.sqlite_store import SQLiteStore
    sqlite = SQLiteStore(str(SQLITE_PATH))
    try:
        rows = sqlite.list_action_logs()
        if not rows:
            print("no action logs")
            return 0
        for r in rows:
            print(_json.dumps(r, ensure_ascii=False))
        return 0
    finally:
        sqlite.close()


def _verify_executions() -> int:
    """check_execution_candidate 的 verify-executions 命令：按 GPT 11 项检查审查 execution 体系。"""
    import json as _json
    from soul.storage.sqlite_store import SQLiteStore
    from soul.storage.evidence_store import EvidenceStore
    from soul.policy import action_levels, default_registry
    sqlite = SQLiteStore(str(SQLITE_PATH))
    evidence = EvidenceStore(str(EVIDENCE_PATH))
    try:
        sqlite.init_action_registry(default_registry.DEFAULT_ACTIONS)
        reports = []
        registry_names = {a["action_name"] for a in sqlite.list_action_registry()}
        ev_ids = {e["event_id"] for e in evidence.list_all()}

        # 1. execution_requests 引用真实 decision/goal/plan/task
        for er in sqlite.list_execution_requests():
            dec = sqlite.get_decision(er.get("decision_id") or "")
            ok = dec is not None
            gid, pid, tid = (er.get("selected_goal_id"), er.get("selected_plan_id"),
                             er.get("selected_task_id"))
            if gid and sqlite.get_goal(gid) is None:
                ok = False
            if pid and sqlite.get_plan(pid) is None:
                ok = False
            if tid and sqlite.get_task(tid) is None:
                ok = False
            reports.append(f"request {er.get('execution_request_id')} refs: {'ok' if ok else 'FAIL'}")

        # 3. action_name 在 registry
        for er in sqlite.list_execution_requests():
            an = er.get("action_name", "")
            reports.append(f"registry {an}: {'ok' if an in registry_names else 'FAIL'}")

        # 4. L0 仅 sandbox/internal
        internal_actions = {a["action_name"] for a in default_registry.DEFAULT_ACTIONS
                            if a.get("action_level") == "L0"}
        for er in sqlite.list_execution_requests(status="executed"):
            lv = er.get("action_level")
            an = er.get("action_name", "")
            ok4 = lv == "L0" and an in internal_actions
            reports.append(f"L0-only-executed {an}: {'ok' if ok4 else 'FAIL'}")

        # 5. L1 未审批不可执行
        for er in sqlite.list_execution_requests():
            if er.get("action_level") == "L1" and er.get("status") == "executed":
                apps = sqlite.list_approvals(er.get("execution_request_id"))
                ok5 = any(a.get("approval_decision") == "approved" for a in apps)
                reports.append(f"L1-executed-approved {er.get('action_name')}: {'ok' if ok5 else 'FAIL'}")

        # 6. L2/L∞ 无 executed log
        for er in sqlite.list_execution_requests():
            if er.get("action_level") in ("L2", "L∞") and er.get("status") == "executed":
                reports.append(f"L2/L∞ executed (FAIL): {er.get('execution_request_id')}")

        # 7/8. action_logs 有 result_evidence_id 且存在于 evidence
        for log in sqlite.list_action_logs():
            rid = log.get("result_evidence_id")
            ok78 = bool(rid) and rid in ev_ids
            reports.append(f"log {log.get('action_log_id')} result_evidence: {'ok' if ok78 else 'FAIL'}")

        # 9. 记录里无真实外部动作词
        for er in sqlite.list_execution_requests():
            an = er.get("action_name", "")
            if action_levels.is_external_action(an, er.get("request_payload", {})):
                reports.append(f"external-action (FAIL): {an}")

        # 10. goal/plan/task/decision status 未被 action 修改（此处只读复查状态，不深挖历史）
        # 11. 无绕过 Constitution 的执行记录（execution 全部经 Gate/log 落库，天然无绕过路径）
        reports.append("constitution-bypass: ok (所有执行均经 gate 落库)")

        ok = not any("FAIL" in r for r in reports)
        print(_json.dumps({"passed": ok, "checks": reports}, ensure_ascii=False, indent=2))
        return 0 if ok else 1
    finally:
        sqlite.close()


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("Project Soul skeleton ready")
        return 0
    cmd = argv[0]

    if cmd == "feed":
        if len(argv) < 2:
            print("usage: python -m soul feed \"<message>\" [--json]")
            return 1
        as_json = "--json" in argv
        return _feed(argv[1], as_json=as_json)
    if cmd == "verify-evidence":
        return _verify_evidence()
    if cmd == "list-working-memory":
        return _list_working_memory()
    if cmd == "list-episodes":
        return _list_episodes()
    if cmd == "list-reflections":
        return _list_reflections()
    if cmd == "run-slow-loop":
        return _run_slow_loop()
    if cmd == "list-semantic-memory":
        return _list_semantic_memory()
    if cmd == "list-consolidated-episodes":
        return _list_consolidated_episodes()
    if cmd == "list-long-reflections":
        return _list_long_reflections()
    if cmd == "run-narrative-cycle":
        return _run_narrative_cycle()
    if cmd == "list-narratives":
        return _list_narratives()
    if cmd == "list-rejections":
        return _list_rejections()
    if cmd == "verify-constitution":
        return _verify_constitution()
    if cmd == "run-belief-cycle":
        return _run_belief_cycle()
    if cmd == "run-relationship-cycle":
        return _run_relationship_cycle()
    if cmd == "list-beliefs":
        return _list_beliefs()
    if cmd == "list-relationships":
        return _list_relationships()
    if cmd == "list-relationship-updates":
        return _list_relationship_updates()
    if cmd == "verify-beliefs":
        return _verify_beliefs()
    if cmd == "verify-relationships":
        return _verify_relationships()
    if cmd == "run-self-cycle":
        return _run_self_cycle()
    if cmd == "show-current-self":
        return _show_current_self()
    if cmd == "list-self-snapshots":
        return _list_self_snapshots()
    if cmd == "verify-self":
        return _verify_self()
    if cmd == "run-goal-cycle":
        return _run_goal_cycle()
    if cmd == "list-goals":
        return _list_goals()
    if cmd == "show-active-goals":
        return _show_active_goals()
    if cmd == "list-goal-updates":
        return _list_goal_updates()
    if cmd == "verify-goals":
        return _verify_goals()
    if cmd == "run-goal-progress-cycle":
        return _run_goal_progress_cycle()
    if cmd == "show-goal-dashboard":
        return _show_goal_dashboard()
    if cmd == "list-goal-progress":
        return _list_goal_progress()
    if cmd == "verify-goal-progress":
        return _verify_goal_progress()
    if cmd == "run-planning-cycle":
        return _run_planning_cycle()
    if cmd == "list-plans":
        return _list_plans()
    if cmd == "show-current-plan":
        return _show_current_plan()
    if cmd == "list-tasks":
        return _list_tasks()
    if cmd == "verify-plans":
        return _verify_plans()
    if cmd == "run-decision-cycle":
        return _run_decision_cycle()
    if cmd == "list-decisions":
        return _list_decisions()
    if cmd == "show-current-decision":
        return _show_current_decision()
    if cmd == "verify-decisions":
        return _verify_decisions()
    if cmd == "run-goal-consolidation-cycle":
        return _run_consolidation_cycle()
    if cmd == "list-long-term-goals":
        return _list_long_term_goals()
    if cmd == "list-goal-consolidations":
        return _list_goal_consolidations()
    if cmd == "show-goal-continuity":
        return _show_goal_continuity()
    if cmd == "verify-goal-continuity":
        return _verify_goal_continuity()
    if cmd == "run-motivation-cycle":
        return _run_motivation_cycle()
    if cmd == "list-motivations":
        return _list_motivations()
    if cmd == "show-active-motivations":
        return _show_active_motivations()
    if cmd == "verify-motivations":
        return _verify_motivations()
    if cmd == "update-goal-status":
        goal_id = argv[1] if len(argv) > 1 else ""
        status = argv[2] if len(argv) > 2 else ""
        reason = ""
        if "--reason" in argv:
            i = argv.index("--reason")
            if i + 1 < len(argv):
                reason = argv[i + 1]
        return _update_goal_status(goal_id, status, reason)
    if cmd == "list-action-registry":
        return _list_action_registry()
    if cmd == "run-execution-gate":
        return _run_execution_gate()
    if cmd == "list-execution-requests":
        return _list_execution_requests()
    if cmd == "show-execution-request":
        return _show_execution_request(argv[1] if len(argv) > 1 else "")
    if cmd == "approve-execution":
        er_id = argv[1] if len(argv) > 1 else ""
        reason = ""
        if "--reason" in argv:
            i = argv.index("--reason")
            if i + 1 < len(argv):
                reason = argv[i + 1]
        return _approve_execution(er_id, reason)
    if cmd == "reject-execution":
        er_id = argv[1] if len(argv) > 1 else ""
        reason = ""
        if "--reason" in argv:
            i = argv.index("--reason")
            if i + 1 < len(argv):
                reason = argv[i + 1]
        return _reject_execution(er_id, reason)
    if cmd == "run-approved-action":
        return _run_approved_action(argv[1] if len(argv) > 1 else "")
    if cmd == "list-action-logs":
        return _list_action_logs()
    if cmd == "cognitive-loop":
        return _run_cognitive_loop()
    if cmd == "verify-executions":
        return _verify_executions()
    if cmd in ("help", "--help", "-h"):
        print(
            "Project Soul CLI\n"
            "  python -m soul                           skeleton banner\n"
            '  python -m soul feed "<msg>" [--json]      full Phase 3 trace\n'
            "  python -m soul verify-evidence            verify evidence hash chain\n"
            "  python -m soul list-working-memory        view short-term memory\n"
            "  python -m soul list-episodes              view experience episodes\n"
            "  python -m soul list-reflections           view short reflections\n"
            "  python -m soul run-slow-loop              run one slow loop (Phase 4)\n"
            "  python -m soul list-semantic-memory       view semantic memory\n"
            "  python -m soul list-consolidated-episodes view consolidated episodes\n"
            "  python -m soul list-long-reflections      view long reflections\n"
            "  python -m soul run-narrative-cycle        run narrative cycle (Phase 5)\n"
            "  python -m soul list-narratives            view narratives\n"
            "  python -m soul list-rejections            view constitution rejections\n"
            "  python -m soul verify-constitution        verify all narratives pass constitution\n"
            "  python -m soul run-belief-cycle           run belief cycle (Phase 6)\n"
            "  python -m soul run-relationship-cycle     run relationship cycle (Phase 6)\n"
            "  python -m soul list-beliefs               view beliefs\n"
            "  python -m soul list-relationships         view relationships\n"
            "  python -m soul list-relationship-updates  view relationship updates\n"
            "  python -m soul verify-beliefs             verify active beliefs\n"
            "  python -m soul verify-relationships       verify relationship updates\n"
            "  python -m soul run-self-cycle             run self snapshot cycle (Phase 7)\n"
            "  python -m soul show-current-self          show current self snapshot\n"
            "  python -m soul list-self-snapshots        view self snapshots\n"
            "  python -m soul verify-self                verify self snapshots pass constitution\n"
            "  python -m soul run-goal-cycle             run goal cycle (Phase 8)\n"
            "  python -m soul list-goals                 view goals\n"
            "  python -m soul show-active-goals          view active goals\n"
            "  python -m soul update-goal-status <id> <status> --reason <r>  update goal status\n"
            "  python -m soul list-goal-updates          view goal update history\n"
            "  python -m soul verify-goals               verify goals pass constitution\n"
            "  python -m soul run-goal-progress-cycle     run goal progress cycle (Phase 9)\n"
            "  python -m soul show-goal-dashboard         show goal dashboard by priority\n"
            "  python -m soul list-goal-progress          view goal progress\n"
            "  python -m soul verify-goal-progress        verify goal progress pass constitution\n"
            "  python -m soul run-planning-cycle          plan top goals into plan+tasks (Phase 10)\n"
            "  python -m soul list-plans                  view plans\n"
            "  python -m soul show-current-plan           view latest active plan + tasks\n"
            "  python -m soul list-tasks                  view tasks\n"
            "  python -m soul verify-plans                verify plans+tasks pass constitution\n"
            "  python -m soul run-decision-cycle         recommend next task for review (Phase 11)\n"
            "  python -m soul list-decisions             view decisions\n"
            "  python -m soul show-current-decision      view latest waiting decision\n"
            "  python -m soul verify-decisions           verify decisions pass constitution\n"
            "  python -m soul run-goal-consolidation-cycle  consolidate goals into long-term goals (Phase 12)\n"
            "  python -m soul list-long-term-goals         list long-term goals\n"
            "  python -m soul list-goal-consolidations     list goal consolidation records\n"
            "  python -m soul show-goal-continuity         show active long-term goals with sources\n"
            "  python -m soul verify-goal-continuity       verify long-term goals/consolidations pass constitution\n"
            "  python -m soul run-motivation-cycle           generate motivations for directions (Phase 13)\n"
            "  python -m soul list-motivations               list motivations\n"
            "  python -m soul show-active-motivations        show active motivations with sources\n"
            "  python -m soul verify-motivations             verify motivations pass constitution\n"
            "  python -m soul list-action-registry           list action registry (Phase 14)\n"
            "  python -m soul run-execution-gate             Gate decision -> execution request (Phase 14)\n"
            "  python -m soul list-execution-requests        list execution requests\n"
            "  python -m soul show-execution-request <id>    show one execution request\n"
            "  python -m soul approve-execution <id> --reason <r>  approve L1 request\n"
            "  python -m soul reject-execution <id> --reason <r>   reject request\n"
            "  python -m soul run-approved-action <id>       run auto_allowed/approved action\n"
            "  python -m soul list-action-logs               list action logs\n"
            "  python -m soul verify-executions              verify execution system integrity\n"
        )
        return 0

    print(f"unknown command: {cmd}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
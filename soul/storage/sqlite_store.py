"""SQLiteStore — 结构化状态存储（Working Memory / Episode / Reflection）。

保存于 data/soul_state.sqlite3。
- 数据库不存在自动创建。
- init_schema() 建表。
- evidence 仍为 append-only JSONL，本库不存放 evidence。
- 所有记录必须引用 event_id / episode_id（Constitution 02）。
- 写入失败返回清楚错误。
"""
from __future__ import annotations
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from soul.storage.base import BaseStore

WORKING_MAX = 50  # 保留最近 N 条，超出的旧记录 archived=1


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


_LTG_LIST_COLS = (
    "evidence_ids_json", "source_goal_ids_json", "source_belief_ids_json",
    "source_narrative_ids_json", "source_semantic_memory_ids_json",
    "source_reflection_ids_json", "source_decision_ids_json",
    "constitution_result_json",
)


def _restore_ltg(d: dict[str, Any]) -> dict[str, Any]:
    """把 long_term_goals 的 *_json 列还原成 list 字段（兼容存 str 或 list），key 去 _json 后缀。"""
    out = dict(d)
    for col in _LTG_LIST_COLS:
        if col in out:
            v = out[col]
            if v is None:
                v = [] if col != "constitution_result_json" else {}
            elif isinstance(v, str):
                try:
                    v = json.loads(v)
                except Exception:
                    v = [] if col != "constitution_result_json" else {}
            out[col[:-5]] = v  # 去 _json，映射回短名（source_goal_ids 等）
    return out


_CONS_LIST_COLS = ("source_goal_ids_json", "evidence_ids_json",
                   "source_progress_ids_json", "source_decision_ids_json")


def _restore_cons(d: dict[str, Any]) -> dict[str, Any]:
    out = dict(d)
    for col in _CONS_LIST_COLS:
        if col in out and out[col] is not None:
            v = out[col]
            if isinstance(v, str):
                try:
                    v = json.loads(v)
                except Exception:
                    v = []
            out[col[:-5]] = v
    return out


_MOT_LIST_COLS = (
    "evidence_ids_json",
    "source_long_term_goal_ids_json", "source_goal_ids_json",
    "source_belief_ids_json", "source_narrative_ids_json",
    "source_semantic_memory_ids_json", "source_reflection_ids_json",
    "source_decision_ids_json", "source_goal_progress_ids_json",
    "constitution_result_json",
)


def _restore_mot(d: dict[str, Any]) -> dict[str, Any]:
    """把 motivations 的 *_json 列还原成 list 字段，key 去 _json 后缀；bool 列还原成 bool。"""
    out = dict(d)
    for col in _MOT_LIST_COLS:
        if col in out:
            v = out[col]
            if v is None:
                v = [] if col != "constitution_result_json" else {}
            elif isinstance(v, str):
                try:
                    v = json.loads(v)
                except Exception:
                    v = [] if col != "constitution_result_json" else {}
            out[col[:-5]] = v
    for bcol in ("manual_review_required", "execution_allowed"):
        if bcol in out and out[bcol] is not None:
            out[bcol] = bool(out[bcol])
    return out


_EXEC_LIST_COLS = (
    "request_payload_json", "evidence_ids_json",
    "source_goal_ids_json", "source_plan_ids_json", "source_task_ids_json",
    "source_decision_ids_json", "risk_factors_json", "gate_result_json",
)


def _restore_exec(d: dict[str, Any]) -> dict[str, Any]:
    """把 execution_requests 的 *_json 列还原成 list/dict 字段；bool 列还原。"""
    out = dict(d)
    for col in _EXEC_LIST_COLS:
        if col in out:
            v = out[col]
            default = [] if col not in ("risk_factors_json", "gate_result_json") else {}
            if v is None:
                v = default
            elif isinstance(v, str):
                try:
                    v = json.loads(v)
                except Exception:
                    v = default
            out[col[:-5]] = v
    for bcol in ("approval_required", "manual_review_required", "execution_allowed"):
        if bcol in out and out[bcol] is not None:
            out[bcol] = bool(out[bcol])
    if "action_level" in out and isinstance(out.get("action_level"), str) \
            and out["action_level"] == "infinity":
        out["action_level"] = "L∞"
    return out


_REG_LIST_COLS = ()


def _restore_reg(d: dict[str, Any]) -> dict[str, Any]:
    """还原 action_registry 行的 JSON/bool 字段。"""
    out = dict(d)
    for bcol in ("enabled", "requires_approval", "banned"):
        if bcol in out and out[bcol] is not None:
            out[bcol] = bool(out[bcol])
    if "action_level" in out and out["action_level"] == "infinity":
        out["action_level"] = "L∞"
    return out


_LOG_LIST_COLS = ("input_payload_json", "output_payload_json")


def _restore_log(d: dict[str, Any]) -> dict[str, Any]:
    """还原 action_logs 行的 JSON 字段。"""
    out = dict(d)
    for col in _LOG_LIST_COLS:
        if col in out:
            v = out[col]
            if v is None:
                v = {}
            elif isinstance(v, str):
                try:
                    v = json.loads(v)
                except Exception:
                    v = {}
            out[col[:-5]] = v
    return out


class SQLiteStore(BaseStore):
    append_only = False

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
            self.init_schema()
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def init_schema(self) -> None:
        conn = self._connect()
        cur = conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS working_memory (
                memory_id TEXT PRIMARY KEY,
                event_id TEXT NOT NULL,
                content TEXT NOT NULL,
                normalized_content TEXT,
                importance_score REAL,
                appraisal_json TEXT,
                source TEXT,
                actor TEXT,
                created_at TEXT,
                expires_at TEXT,
                retrieval_weight REAL DEFAULT 1.0,
                archived INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS episodes (
                episode_id TEXT PRIMARY KEY,
                start_time TEXT,
                end_time TEXT,
                summary TEXT,
                event_ids_json TEXT,
                actors_json TEXT,
                outcome TEXT,
                importance_score REAL,
                emotional_trace_json TEXT,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS reflections (
                reflection_id TEXT PRIMARY KEY,
                reflection_type TEXT DEFAULT 'short',
                episode_id TEXT,
                event_id TEXT,
                content TEXT,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS consolidated_episodes (
                consolidated_episode_id TEXT PRIMARY KEY,
                source_episode_ids_json TEXT,
                source_event_ids_json TEXT,
                start_time TEXT,
                end_time TEXT,
                summary TEXT,
                actors_json TEXT,
                importance_score REAL,
                emotional_trace_json TEXT,
                tags_json TEXT,
                consolidation_reason TEXT,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS semantic_memory (
                memory_id TEXT PRIMARY KEY,
                memory_type TEXT DEFAULT 'semantic',
                content TEXT,
                source_episode_ids_json TEXT,
                source_event_ids_json TEXT,
                confidence REAL,
                importance REAL,
                retrieval_weight REAL DEFAULT 1.0,
                decay_score REAL DEFAULT 0.0,
                created_at TEXT,
                updated_at TEXT,
                archived INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS long_reflections (
                reflection_id TEXT PRIMARY KEY,
                episode_id TEXT,
                consolidated_episode_id TEXT,
                event_id TEXT,
                event_ids_json TEXT,
                content TEXT,
                summary TEXT,
                observations_json TEXT,
                candidate_updates_json TEXT,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS narratives (
                narrative_id TEXT PRIMARY KEY,
                title TEXT,
                narrative_type TEXT,
                content TEXT,
                meaning TEXT,
                identity_effect TEXT,
                evidence_ids_json TEXT,
                episode_ids_json TEXT,
                consolidated_episode_id TEXT,
                semantic_memory_ids_json TEXT,
                version INTEGER DEFAULT 1,
                supersedes TEXT,
                status TEXT,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS constitution_rejections (
                rejection_id TEXT PRIMARY KEY,
                candidate_type TEXT,
                candidate_id TEXT,
                check_name TEXT,
                reason TEXT,
                candidate_json TEXT,
                evidence_refs_json TEXT,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS beliefs (
                belief_id TEXT PRIMARY KEY,
                statement TEXT,
                belief_type TEXT,
                confidence REAL,
                evidence_ids_json TEXT,
                supporting_episode_ids_json TEXT,
                source_narrative_ids_json TEXT,
                source_semantic_memory_ids_json TEXT,
                contradiction_ids_json TEXT,
                version INTEGER DEFAULT 1,
                supersedes TEXT,
                status TEXT,
                created_at TEXT,
                updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS relationships (
                person_id TEXT PRIMARY KEY,
                name TEXT,
                trust REAL,
                familiarity REAL,
                importance REAL,
                affinity REAL,
                shared_goals_json TEXT,
                conflict_history_json TEXT,
                evidence_ids_json TEXT,
                supporting_episode_ids_json TEXT,
                last_interaction_at TEXT,
                version INTEGER DEFAULT 1,
                created_at TEXT,
                updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS relationship_updates (
                update_id TEXT PRIMARY KEY,
                person_id TEXT,
                field_changed TEXT,
                old_value REAL,
                new_value REAL,
                delta REAL,
                reason TEXT,
                evidence_ids_json TEXT,
                episode_ids_json TEXT,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS self_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                timestamp TEXT,
                identity_summary TEXT,
                active_beliefs_json TEXT,
                active_relationships_json TEXT,
                active_goals_json TEXT,
                dominant_narratives_json TEXT,
                semantic_memory_refs_json TEXT,
                current_emotion_state_json TEXT,
                confidence_profile_json TEXT,
                change_log_json TEXT,
                evidence_refs_json TEXT,
                source_belief_ids_json TEXT,
                source_relationship_ids_json TEXT,
                source_narrative_ids_json TEXT,
                source_semantic_memory_ids_json TEXT,
                previous_snapshot_id TEXT,
                similarity_to_previous REAL,
                version INTEGER DEFAULT 1,
                status TEXT,
                constitution_result_json TEXT,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS goals (
                goal_id TEXT PRIMARY KEY,
                parent_goal_id TEXT,
                title TEXT,
                description TEXT,
                goal_type TEXT,
                status TEXT,
                priority REAL,
                milestone_refs TEXT,
                constitution_refs TEXT,
                evidence_ids JSON,
                source_belief_ids JSON,
                source_narrative_ids JSON,
                source_semantic_memory_ids JSON,
                source_reflection_ids JSON,
                related_relationship_ids JSON,
                version INTEGER DEFAULT 1,
                supersedes TEXT,
                created_at TEXT,
                updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS goal_updates (
                update_id TEXT PRIMARY KEY,
                goal_id TEXT,
                old_status TEXT,
                new_status TEXT,
                old_priority REAL,
                new_priority REAL,
                reason TEXT,
                evidence_ids JSON,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS goal_progress (
                progress_id TEXT PRIMARY KEY,
                goal_id TEXT,
                progress_value REAL,
                progress_delta REAL,
                progress_status TEXT,
                evidence_ids JSON,
                source_episode_ids JSON,
                source_narrative_ids JSON,
                source_semantic_memory_ids JSON,
                source_reflection_ids JSON,
                source_goal_update_ids JSON,
                reason TEXT,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS plans (
                plan_id TEXT PRIMARY KEY,
                goal_id TEXT,
                title TEXT,
                description TEXT,
                plan_type TEXT,
                status TEXT,
                priority REAL,
                evidence_ids_json JSON,
                source_goal_ids_json JSON,
                source_belief_ids_json JSON,
                source_narrative_ids_json JSON,
                source_semantic_memory_ids_json JSON,
                source_reflection_ids_json JSON,
                source_goal_progress_ids_json JSON,
                source_consolidated_episode_ids_json JSON,
                task_ids_json JSON,
                version INTEGER,
                supersedes TEXT,
                constitution_result_json JSON,
                created_at TEXT,
                updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                plan_id TEXT,
                goal_id TEXT,
                title TEXT,
                description TEXT,
                task_type TEXT,
                status TEXT,
                order_index INTEGER,
                priority REAL,
                evidence_ids_json JSON,
                depends_on_task_ids_json JSON,
                expected_output TEXT,
                execution_mode TEXT,
                created_at TEXT,
                updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS decisions (
                decision_id TEXT PRIMARY KEY,
                decision_type TEXT,
                status TEXT,
                selected_goal_id TEXT,
                selected_plan_id TEXT,
                selected_task_id TEXT,
                selected_task_title TEXT,
                reason TEXT,
                decision_factors_json JSON,
                evidence_ids_json JSON,
                source_goal_ids_json JSON,
                source_plan_ids_json JSON,
                source_task_ids_json JSON,
                source_belief_ids_json JSON,
                source_narrative_ids_json JSON,
                source_semantic_memory_ids_json JSON,
                source_goal_progress_ids_json JSON,
                manual_review_required INTEGER,
                execution_allowed INTEGER,
                constitution_result_json JSON,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS long_term_goals (
                long_term_goal_id TEXT PRIMARY KEY,
                title TEXT,
                description TEXT,
                goal_type TEXT,
                status TEXT,
                priority REAL,
                progress_value REAL,
                evidence_ids_json JSON,
                source_goal_ids_json JSON,
                source_belief_ids_json JSON,
                source_narrative_ids_json JSON,
                source_semantic_memory_ids_json JSON,
                source_reflection_ids_json JSON,
                source_decision_ids_json JSON,
                continuity_reason TEXT,
                version INTEGER,
                supersedes TEXT,
                constitution_result_json JSON,
                created_at TEXT,
                updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS goal_consolidations (
                consolidation_id TEXT PRIMARY KEY,
                long_term_goal_id TEXT,
                source_goal_ids_json JSON,
                consolidation_type TEXT,
                reason TEXT,
                evidence_ids_json JSON,
                source_progress_ids_json JSON,
                source_decision_ids_json JSON,
                action_taken TEXT,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS motivations (
                motivation_id TEXT PRIMARY KEY,
                motivation_type TEXT,
                status TEXT,
                direction TEXT,
                reason TEXT,
                motivation_score REAL,
                priority REAL,
                evidence_ids_json JSON,
                source_long_term_goal_ids_json JSON,
                source_goal_ids_json JSON,
                source_belief_ids_json JSON,
                source_narrative_ids_json JSON,
                source_semantic_memory_ids_json JSON,
                source_reflection_ids_json JSON,
                source_decision_ids_json JSON,
                source_goal_progress_ids_json JSON,
                manual_review_required INTEGER,
                execution_allowed INTEGER,
                version INTEGER,
                supersedes TEXT,
                constitution_result_json JSON,
                created_at TEXT,
                updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS action_registry (
                action_name TEXT PRIMARY KEY,
                action_level TEXT,
                description TEXT,
                enabled INTEGER,
                allowed_scope TEXT,
                daily_limit INTEGER,
                requires_approval INTEGER,
                banned INTEGER,
                created_at TEXT,
                updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS execution_requests (
                execution_request_id TEXT PRIMARY KEY,
                decision_id TEXT,
                selected_goal_id TEXT,
                selected_plan_id TEXT,
                selected_task_id TEXT,
                action_name TEXT,
                action_level TEXT,
                status TEXT,
                approval_required INTEGER,
                manual_review_required INTEGER,
                execution_allowed INTEGER,
                reason TEXT,
                request_payload_json JSON,
                evidence_ids_json JSON,
                source_goal_ids_json JSON,
                source_plan_ids_json JSON,
                source_task_ids_json JSON,
                source_decision_ids_json JSON,
                risk_factors_json JSON,
                gate_result_json JSON,
                created_at TEXT,
                updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS execution_approvals (
                approval_id TEXT PRIMARY KEY,
                execution_request_id TEXT,
                reviewer TEXT,
                approval_decision TEXT,
                reason TEXT,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS action_logs (
                action_log_id TEXT PRIMARY KEY,
                execution_request_id TEXT,
                action_name TEXT,
                action_level TEXT,
                status TEXT,
                input_payload_json JSON,
                output_payload_json JSON,
                result_summary TEXT,
                result_evidence_id TEXT,
                created_at TEXT
            );
            -- Phase 15A: Soul Feed Layer — 外部待办源（感知入口）
            CREATE TABLE IF NOT EXISTS work_items (
                work_item_id TEXT PRIMARY KEY,
                source TEXT,
                source_id TEXT,
                work_type TEXT,
                title TEXT,
                description TEXT,
                priority_hint TEXT,
                related_goal_ids_json JSON,
                related_plan_ids_json JSON,
                evidence_ids_json JSON,
                status TEXT,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS action_candidates (
                candidate_id TEXT PRIMARY KEY,
                work_item_id TEXT,
                action_name TEXT,
                action_level TEXT,
                payload_json JSON,
                risk_factors_json JSON,
                evidence_ids_json JSON,
                source TEXT,
                status TEXT,
                created_at TEXT
            );
            """
        )
        conn.commit()
        # 迁移：decisions 表可选列 related_{long_term_goal,motivation}_ids_json（已存在则忽略）
        cols = {r[1] for r in conn.execute("PRAGMA table_info(decisions)")}
        if "related_long_term_goal_ids_json" not in cols:
            try:
                conn.execute(
                    "ALTER TABLE decisions ADD COLUMN related_long_term_goal_ids_json JSON")
                conn.commit()
            except sqlite3.OperationalError:
                pass  # 并发/已存在
        if "related_motivation_ids_json" not in cols:
            try:
                conn.execute(
                    "ALTER TABLE decisions ADD COLUMN related_motivation_ids_json JSON")
                conn.commit()
            except sqlite3.OperationalError:
                pass  # 并发/已存在

    # ---------- Working Memory ----------
    def add_working_memory(self, mem: dict[str, Any]) -> str:
        conn = self._connect()
        cur = conn.cursor()
        try:
            cur.execute(
                """INSERT INTO working_memory
                   (memory_id, event_id, content, normalized_content, importance_score,
                    appraisal_json, source, actor, created_at, expires_at,
                    retrieval_weight, archived)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    mem["memory_id"],
                    mem["event_id"],
                    mem["content"],
                    mem.get("normalized_content"),
                    mem.get("importance_score"),
                    json.dumps(mem.get("appraisal", {}), ensure_ascii=False),
                    mem.get("source"),
                    mem.get("actor"),
                    mem.get("created_at"),
                    mem.get("expires_at"),
                    mem.get("retrieval_weight", 1.0),
                    int(mem.get("archived", False)),
                ),
            )
            conn.commit()
            self._cap_working_memory()
            return mem["memory_id"]
        except Exception as e:
            raise RuntimeError(f"add_working_memory failed: {e}")

    def _cap_working_memory(self) -> None:
        """保留最近 WORKING_MAX 条，更早的 archived=1。"""
        cur = self._connect().cursor()
        cur.execute(
            """UPDATE working_memory SET archived=1 WHERE memory_id NOT IN (
                   SELECT memory_id FROM working_memory
                   ORDER BY created_at DESC LIMIT ?)""",
            (WORKING_MAX,),
        )
        self._conn.commit()

    def list_working_memory(self, active_only: bool = True) -> list[dict[str, Any]]:
        cur = self._connect().cursor()
        if active_only:
            cur.execute(
                "SELECT * FROM working_memory WHERE archived=0 ORDER BY created_at DESC"
            )
        else:
            cur.execute("SELECT * FROM working_memory ORDER BY created_at DESC")
        return [dict(r) for r in cur.fetchall()]

    # ---------- Episode ----------
    def add_episode(self, ep: dict[str, Any]) -> str:
        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO episodes
                   (episode_id, start_time, end_time, summary, event_ids_json,
                    actors_json, outcome, importance_score, emotional_trace_json, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    ep["episode_id"],
                    ep.get("start_time"),
                    ep.get("end_time"),
                    ep.get("summary", ""),
                    json.dumps(ep.get("event_ids", []), ensure_ascii=False),
                    json.dumps(ep.get("actors", []), ensure_ascii=False),
                    ep.get("outcome"),
                    ep.get("importance_score", 0.0),
                    json.dumps(ep.get("emotional_trace", {}), ensure_ascii=False),
                    ep.get("created_at"),
                ),
            )
            conn.commit()
            return ep["episode_id"]
        except Exception as e:
            raise RuntimeError(f"add_episode failed: {e}")

    def list_episodes(self) -> list[dict[str, Any]]:
        cur = self._connect().cursor()
        cur.execute("SELECT * FROM episodes ORDER BY created_at DESC")
        return [dict(r) for r in cur.fetchall()]

    # ---------- Reflection ----------
    def add_reflection(self, ref: dict[str, Any]) -> str:
        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO reflections
                   (reflection_id, reflection_type, episode_id, event_id, content, created_at)
                   VALUES (?,?,?,?,?,?)""",
                (
                    ref["reflection_id"],
                    ref.get("reflection_type", "short"),
                    ref.get("episode_id"),
                    ref.get("event_id"),
                    ref.get("content", ""),
                    ref.get("created_at"),
                ),
            )
            conn.commit()
            return ref["reflection_id"]
        except Exception as e:
            raise RuntimeError(f"add_reflection failed: {e}")

    def list_reflections(self, type_filter: str | None = None) -> list[dict[str, Any]]:
        cur = self._connect().cursor()
        if type_filter:
            cur.execute(
                "SELECT * FROM reflections WHERE reflection_type=? ORDER BY created_at DESC",
                (type_filter,),
            )
        else:
            cur.execute("SELECT * FROM reflections ORDER BY created_at DESC")
        return [dict(r) for r in cur.fetchall()]

    # ---------- Long Reflection ----------
    def add_long_reflection(self, lr: dict[str, Any]) -> str:
        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO long_reflections
                   (reflection_id, episode_id, consolidated_episode_id, event_id,
                    event_ids_json, content, summary, observations_json,
                    candidate_updates_json, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    lr["reflection_id"],
                    lr.get("episode_id"),
                    lr.get("consolidated_episode_id"),
                    lr.get("event_id"),
                    json.dumps(lr.get("event_ids", []), ensure_ascii=False),
                    lr.get("content", ""),
                    lr.get("summary", ""),
                    json.dumps(lr.get("observations", []), ensure_ascii=False),
                    json.dumps(lr.get("candidate_updates", []), ensure_ascii=False),
                    lr.get("created_at"),
                ),
            )
            conn.commit()
            return lr["reflection_id"]
        except Exception as e:
            raise RuntimeError(f"add_long_reflection failed: {e}")

    def list_long_reflections(self) -> list[dict[str, Any]]:
        cur = self._connect().cursor()
        cur.execute("SELECT * FROM long_reflections ORDER BY created_at DESC")
        return [dict(r) for r in cur.fetchall()]

    # ---------- Narrative ----------
    def add_narrative(self, nar: dict[str, Any]) -> str:
        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO narratives
                   (narrative_id, title, narrative_type, content, meaning, identity_effect,
                    evidence_ids_json, episode_ids_json, consolidated_episode_id,
                    semantic_memory_ids_json, version, supersedes, status, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    nar["narrative_id"],
                    nar.get("title", ""),
                    nar.get("narrative_type", "general"),
                    nar.get("content", ""),
                    nar.get("meaning", ""),
                    nar.get("identity_effect", ""),
                    json.dumps(nar.get("evidence_ids", []), ensure_ascii=False),
                    json.dumps(nar.get("episode_ids", []), ensure_ascii=False),
                    nar.get("consolidated_episode_id"),
                    json.dumps(nar.get("semantic_memory_ids", []), ensure_ascii=False),
                    nar.get("version", 1),
                    nar.get("supersedes"),
                    nar.get("status", "accepted"),
                    nar.get("created_at"),
                ),
            )
            conn.commit()
            return nar["narrative_id"]
        except Exception as e:
            raise RuntimeError(f"add_narrative failed: {e}")

    def list_narratives(self) -> list[dict[str, Any]]:
        cur = self._connect().cursor()
        cur.execute("SELECT * FROM narratives ORDER BY created_at DESC")
        return [dict(r) for r in cur.fetchall()]

    def get_narrative(self, narrative_id: str) -> dict[str, Any] | None:
        cur = self._connect().cursor()
        cur.execute("SELECT * FROM narratives WHERE narrative_id=?", (narrative_id,))
        r = cur.fetchone()
        return dict(r) if r else None

    def next_narrative_version(self, superseded_id: str | None = None) -> int:
        """对某个被 supersede 的 narrative 返回下一版本号（默认 1）。"""
        if not superseded_id:
            return 1
        cur = self._connect().cursor()
        cur.execute("SELECT version FROM narratives WHERE narrative_id=?", (superseded_id,))
        r = cur.fetchone()
        return (r["version"] + 1) if r else 1

    # ---------- Constitution Rejection ----------
    def add_rejection(self, rej: dict[str, Any]) -> str:
        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO constitution_rejections
                   (rejection_id, candidate_type, candidate_id, check_name, reason,
                    candidate_json, evidence_refs_json, created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    rej["rejection_id"],
                    rej.get("candidate_type", "narrative"),
                    rej.get("candidate_id"),
                    rej.get("check_name", ""),
                    rej.get("reason", ""),
                    json.dumps(rej.get("candidate", {}), ensure_ascii=False),
                    json.dumps(rej.get("evidence_refs", []), ensure_ascii=False),
                    rej.get("created_at"),
                ),
            )
            conn.commit()
            return rej["rejection_id"]
        except Exception as e:
            raise RuntimeError(f"add_rejection failed: {e}")

    def list_rejections(self) -> list[dict[str, Any]]:
        cur = self._connect().cursor()
        cur.execute("SELECT * FROM constitution_rejections ORDER BY created_at DESC")
        return [dict(r) for r in cur.fetchall()]

    # ---------- Belief ----------
    def add_belief(self, bel: dict[str, Any]) -> str:
        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO beliefs
                   (belief_id, statement, belief_type, confidence, evidence_ids_json,
                    supporting_episode_ids_json, source_narrative_ids_json,
                    source_semantic_memory_ids_json, contradiction_ids_json,
                    version, supersedes, status, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    bel["belief_id"],
                    bel.get("statement", ""),
                    bel.get("belief_type", "general"),
                    bel.get("confidence", 0.5),
                    json.dumps(bel.get("evidence_ids", []), ensure_ascii=False),
                    json.dumps(bel.get("supporting_episode_ids", []), ensure_ascii=False),
                    json.dumps(bel.get("source_narrative_ids", []), ensure_ascii=False),
                    json.dumps(bel.get("source_semantic_memory_ids", []), ensure_ascii=False),
                    json.dumps(bel.get("contradiction_ids", []), ensure_ascii=False),
                    bel.get("version", 1),
                    bel.get("supersedes"),
                    bel.get("status", "active"),
                    bel.get("created_at"),
                    bel.get("updated_at"),
                ),
            )
            conn.commit()
            return bel["belief_id"]
        except Exception as e:
            raise RuntimeError(f"add_belief failed: {e}")

    def list_beliefs(self, active_only: bool = True) -> list[dict[str, Any]]:
        cur = self._connect().cursor()
        if active_only:
            cur.execute("SELECT * FROM beliefs WHERE status='active' ORDER BY created_at DESC")
        else:
            cur.execute("SELECT * FROM beliefs ORDER BY created_at DESC")
        return [dict(r) for r in cur.fetchall()]

    def get_belief(self, belief_id: str) -> dict[str, Any] | None:
        cur = self._connect().cursor()
        cur.execute("SELECT * FROM beliefs WHERE belief_id=?", (belief_id,))
        r = cur.fetchone()
        return dict(r) if r else None

    def update_belief_status(self, belief_id: str, status: str) -> None:
        conn = self._connect()
        conn.execute("UPDATE beliefs SET status=? WHERE belief_id=?", (status, belief_id))
        conn.commit()

    # ---------- Relationship ----------
    def add_relationship(self, rel: dict[str, Any]) -> str:
        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO relationships
                   (person_id, name, trust, familiarity, importance, affinity,
                    shared_goals_json, conflict_history_json,
                    evidence_ids_json, supporting_episode_ids_json,
                    last_interaction_at, version, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    rel["person_id"],
                    rel.get("name", rel["person_id"]),
                    round(rel.get("trust", 0.5), 4),
                    round(rel.get("familiarity", 0.3), 4),
                    round(rel.get("importance", 0.3), 4),
                    round(rel.get("affinity", 0.3), 4),
                    json.dumps(rel.get("shared_goals", []), ensure_ascii=False),
                    json.dumps(rel.get("conflict_history", []), ensure_ascii=False),
                    json.dumps(rel.get("evidence_ids", []), ensure_ascii=False),
                    json.dumps(rel.get("supporting_episode_ids", []), ensure_ascii=False),
                    rel.get("last_interaction_at"),
                    rel.get("version", 1),
                    rel.get("created_at"),
                    rel.get("updated_at"),
                ),
            )
            conn.commit()
            return rel["person_id"]
        except Exception as e:
            raise RuntimeError(f"add_relationship failed: {e}")

    def get_relationship(self, person_id: str) -> dict[str, Any] | None:
        cur = self._connect().cursor()
        cur.execute("SELECT * FROM relationships WHERE person_id=?", (person_id,))
        r = cur.fetchone()
        return dict(r) if r else None

    def update_relationship_scores(self, person_id: str, **fields) -> None:
        """按字段名更新 trust/familiarity/importance/affinity 等。"""
        conn = self._connect()
        allowed = {"trust", "familiarity", "importance", "affinity",
                   "last_interaction_at", "updated_at", "shared_goals", "conflict_history"}
        sets, vals = [], []
        for k, v in fields.items():
            if k not in allowed:
                continue
            if k in ("shared_goals", "conflict_history"):
                if not isinstance(v, str):
                    v = json.dumps(v, ensure_ascii=False)
                sets.append(f"{k}={chr(63)}".replace(chr(63), k) + " = ?")
            else:
                sets.append(f"{k} = ?")
            vals.append(v)
        if not sets:
            return
        vals.append(person_id)
        conn.execute(f"UPDATE relationships SET {', '.join(sets)} WHERE person_id=?", vals)
        conn.commit()

    def list_relationships(self) -> list[dict[str, Any]]:
        cur = self._connect().cursor()
        cur.execute("SELECT * FROM relationships ORDER BY updated_at DESC")
        return [dict(r) for r in cur.fetchall()]

    # ---------- Relationship Update（log） ----------
    def add_relationship_update(self, upd: dict[str, Any]) -> str:
        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO relationship_updates
                   (update_id, person_id, field_changed, old_value, new_value, delta,
                    reason, evidence_ids_json, episode_ids_json, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    upd["update_id"],
                    upd["person_id"],
                    upd.get("field_changed", ""),
                    upd.get("old_value"),
                    upd.get("new_value"),
                    upd.get("delta"),
                    upd.get("reason", ""),
                    json.dumps(upd.get("evidence_ids", []), ensure_ascii=False),
                    json.dumps(upd.get("episode_ids", []), ensure_ascii=False),
                    upd.get("created_at"),
                ),
            )
            conn.commit()
            return upd["update_id"]
        except Exception as e:
            raise RuntimeError(f"add_relationship_update failed: {e}")

    def list_relationship_updates(self) -> list[dict[str, Any]]:
        cur = self._connect().cursor()
        cur.execute("SELECT * FROM relationship_updates ORDER BY created_at DESC")
        return [dict(r) for r in cur.fetchall()]

    # ---------- Self Snapshot ----------
    def add_self_snapshot(self, snap: dict[str, Any]) -> str:
        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO self_snapshots
                   (snapshot_id, timestamp, identity_summary, active_beliefs_json,
                    active_relationships_json, active_goals_json, dominant_narratives_json,
                    semantic_memory_refs_json, current_emotion_state_json,
                    confidence_profile_json, change_log_json, evidence_refs_json,
                    source_belief_ids_json, source_relationship_ids_json,
                    source_narrative_ids_json, source_semantic_memory_ids_json,
                    previous_snapshot_id, similarity_to_previous, version, status,
                    constitution_result_json, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    snap["snapshot_id"],
                    snap.get("timestamp"),
                    snap.get("identity_summary", ""),
                    json.dumps(snap.get("active_beliefs", []), ensure_ascii=False),
                    json.dumps(snap.get("active_relationships", []), ensure_ascii=False),
                    json.dumps(snap.get("active_goals", []), ensure_ascii=False),
                    json.dumps(snap.get("dominant_narratives", []), ensure_ascii=False),
                    json.dumps(snap.get("semantic_memory_refs", []), ensure_ascii=False),
                    json.dumps(snap.get("current_emotion_state", {}), ensure_ascii=False),
                    json.dumps(snap.get("confidence_profile", {}), ensure_ascii=False),
                    json.dumps(snap.get("change_log", []), ensure_ascii=False),
                    json.dumps(snap.get("evidence_refs", []), ensure_ascii=False),
                    json.dumps(snap.get("source_belief_ids", []), ensure_ascii=False),
                    json.dumps(snap.get("source_relationship_ids", []), ensure_ascii=False),
                    json.dumps(snap.get("source_narrative_ids", []), ensure_ascii=False),
                    json.dumps(snap.get("source_semantic_memory_ids", []), ensure_ascii=False),
                    snap.get("previous_snapshot_id"),
                    snap.get("similarity_to_previous"),
                    snap.get("version", 1),
                    snap.get("status", "active"),
                    json.dumps(snap.get("constitution_result", {}), ensure_ascii=False),
                    snap.get("created_at"),
                ),
            )
            conn.commit()
            return snap["snapshot_id"]
        except Exception as e:
            raise RuntimeError(f"add_self_snapshot failed: {e}")

    def list_self_snapshots(self) -> list[dict[str, Any]]:
        cur = self._connect().cursor()
        cur.execute("SELECT * FROM self_snapshots ORDER BY created_at DESC")
        return [dict(r) for r in cur.fetchall()]

    def get_latest_snapshot(self) -> dict[str, Any] | None:
        cur = self._connect().cursor()
        cur.execute("SELECT * FROM self_snapshots ORDER BY created_at DESC LIMIT 1")
        r = cur.fetchone()
        return dict(r) if r else None

    def next_snapshot_version(self) -> int:
        latest = self.get_latest_snapshot()
        return (latest.get("version", 0) + 1) if latest else 1

    # ---------- Goals ----------
    def add_goal(self, goal: dict[str, Any]) -> str:
        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO goals
                  (goal_id, parent_goal_id, title, description, goal_type, status,
                   priority, milestone_refs, constitution_refs, evidence_ids,
                   source_belief_ids, source_narrative_ids, source_semantic_memory_ids,
                   source_reflection_ids, related_relationship_ids, version, supersedes,
                   created_at, updated_at)
                  VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    goal["goal_id"],
                    goal.get("parent_goal_id"),
                    goal.get("title", ""),
                    goal.get("description", ""),
                    goal.get("goal_type", "general"),
                    goal.get("status", "candidate"),
                    goal.get("priority", 0.0),
                    goal.get("milestone_refs"),
                    goal.get("constitution_refs"),
                    json.dumps(goal.get("evidence_ids", []), ensure_ascii=False),
                    json.dumps(goal.get("source_belief_ids", []), ensure_ascii=False),
                    json.dumps(goal.get("source_narrative_ids", []), ensure_ascii=False),
                    json.dumps(goal.get("source_semantic_memory_ids", []), ensure_ascii=False),
                    json.dumps(goal.get("source_reflection_ids", []), ensure_ascii=False),
                    json.dumps(goal.get("related_relationship_ids", []), ensure_ascii=False),
                    goal.get("version", 1),
                    goal.get("supersedes"),
                    goal.get("created_at"),
                    goal.get("updated_at"),
                ),
            )
            conn.commit()
            return goal["goal_id"]
        except Exception as e:
            raise RuntimeError(f"add_goal failed: {e}")

    def list_goals(self) -> list[dict[str, Any]]:
        cur = self._connect().cursor()
        cur.execute("SELECT * FROM goals ORDER BY created_at DESC")
        return [dict(r) for r in cur.fetchall()]

    def get_goal(self, goal_id: str) -> dict[str, Any] | None:
        cur = self._connect().cursor()
        cur.execute("SELECT * FROM goals WHERE goal_id = ?", (goal_id,))
        r = cur.fetchone()
        return dict(r) if r else None

    def list_active_goals(self) -> list[dict[str, Any]]:
        cur = self._connect().cursor()
        cur.execute("SELECT * FROM goals WHERE status = 'active' ORDER BY priority DESC, created_at DESC")
        return [dict(r) for r in cur.fetchall()]

    def next_goal_version(self, goal_id: str) -> int:
        cur = self._connect().cursor()
        cur.execute("SELECT version FROM goals WHERE goal_id = ? ORDER BY version DESC LIMIT 1", (goal_id,))
        r = cur.fetchone()
        return (r["version"] + 1) if r else 1

    def update_goal_status(self, goal_id: str, new_status: str, reason: str,
                           evidence_ids: list | None = None,
                           old_status: str | None = None,
                           new_priority: float | None = None) -> str:
        """更新 goal status，写入 goal_updates。reason 必填，否则报错。"""
        if not reason or not reason.strip():
            raise ValueError("update_goal_status requires a non-empty reason")
        goal = self.get_goal(goal_id)
        if not goal:
            raise KeyError(f"goal {goal_id} not found")
        if old_status is None:
            old_status = goal.get("status", "candidate")
        old_priority = goal.get("priority")
        conn = self._connect()
        update_id = f"gu-{uuid.uuid4()}"
        try:
            conn.execute(
                "UPDATE goals SET status=?, updated_at=? WHERE goal_id=?",
                (new_status, _utc_now(), goal_id),
            )
            conn.commit()
            conn.execute(
                """INSERT INTO goal_updates
                  (update_id, goal_id, old_status, new_status, old_priority, new_priority,
                   reason, evidence_ids, created_at)
                  VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    update_id,
                    goal_id,
                    old_status,
                    new_status,
                    old_priority,
                    new_priority,
                    reason,
                    json.dumps(evidence_ids or [], ensure_ascii=False),
                    _utc_now(),
                ),
            )
            conn.commit()
            return update_id
        except Exception as e:
            raise RuntimeError(f"update_goal_status failed: {e}")

    def list_goal_updates(self) -> list[dict[str, Any]]:
        cur = self._connect().cursor()
        cur.execute("SELECT * FROM goal_updates ORDER BY created_at DESC")
        return [dict(r) for r in cur.fetchall()]

    # ---------- Goal Priority ----------
    def update_goal_priority(self, goal_id: str, computed_priority: float,
                             reason: str, evidence_ids: list | None = None) -> str:
        """更新 goal 的 computed_priority。reason 必填 + 引 evidence。返回 update_id。"""
        if not reason or not reason.strip():
            raise ValueError("update_goal_priority requires a non-empty reason")
        goal = self.get_goal(goal_id)
        if not goal:
            raise KeyError(f"goal {goal_id} not found")
        old_priority = goal.get("priority")
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE goals SET priority=?, updated_at=? WHERE goal_id=?",
                (computed_priority, _utc_now(), goal_id),
            )
            conn.execute(
                """INSERT INTO goal_updates
                  (update_id, goal_id, old_status, new_status, old_priority, new_priority,
                   reason, evidence_ids, created_at)
                  VALUES (?,?,?,?,?,?,?,?,?)""",
                (f"gu-{uuid.uuid4()}", goal_id, goal.get("status"), goal.get("status"),
                 old_priority, computed_priority, reason,
                 json.dumps(evidence_ids or [], ensure_ascii=False), _utc_now()),
            )
            conn.commit()
            return "ok"
        except Exception as e:
            raise RuntimeError(f"update_goal_priority failed: {e}")

    def get_goal_priority_trace(self, goal_id: str) -> list[dict[str, Any]]:
        cur = self._connect().cursor()
        cur.execute("SELECT * FROM goal_updates WHERE goal_id=? AND old_priority IS NOT NULL "
                    "AND old_priority != new_priority ORDER BY created_at DESC", (goal_id,))
        return [dict(r) for r in cur.fetchall()]

    # ---------- Goal Progress ----------
    def add_goal_progress(self, prog: dict[str, Any]) -> str:
        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO goal_progress
                  (progress_id, goal_id, progress_value, progress_delta, progress_status,
                   evidence_ids, source_episode_ids, source_narrative_ids,
                   source_semantic_memory_ids, source_reflection_ids, source_goal_update_ids,
                   reason, created_at)
                  VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    prog["progress_id"], prog.get("goal_id"),
                    prog.get("progress_value"), prog.get("progress_delta"),
                    prog.get("progress_status"),
                    json.dumps(prog.get("evidence_ids", []), ensure_ascii=False),
                    json.dumps(prog.get("source_episode_ids", []), ensure_ascii=False),
                    json.dumps(prog.get("source_narrative_ids", []), ensure_ascii=False),
                    json.dumps(prog.get("source_semantic_memory_ids", []), ensure_ascii=False),
                    json.dumps(prog.get("source_reflection_ids", []), ensure_ascii=False),
                    json.dumps(prog.get("source_goal_update_ids", []), ensure_ascii=False),
                    prog.get("reason", ""),
                    prog.get("created_at"),
                ),
            )
            conn.commit()
            return prog["progress_id"]
        except Exception as e:
            raise RuntimeError(f"add_goal_progress failed: {e}")

    def get_latest_goal_progress(self, goal_id: str) -> dict[str, Any] | None:
        cur = self._connect().cursor()
        cur.execute("SELECT * FROM goal_progress WHERE goal_id=? "
                    "ORDER BY created_at DESC LIMIT 1", (goal_id,))
        r = cur.fetchone()
        return dict(r) if r else None

    def list_goal_progress(self) -> list[dict[str, Any]]:
        cur = self._connect().cursor()
        cur.execute("SELECT * FROM goal_progress ORDER BY created_at DESC")
        return [dict(r) for r in cur.fetchall()]

    def list_goal_progress_for(self, goal_id: str) -> list[dict[str, Any]]:
        cur = self._connect().cursor()
        cur.execute("SELECT * FROM goal_progress WHERE goal_id=? "
                    "ORDER BY created_at DESC", (goal_id,))
        return [dict(r) for r in cur.fetchall()]

    # ---------- Consolidated Episode ----------
    def add_consolidated_episode(self, ce: dict[str, Any]) -> str:
        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO consolidated_episodes
                   (consolidated_episode_id, source_episode_ids_json, source_event_ids_json,
                    start_time, end_time, summary, actors_json, importance_score,
                    emotional_trace_json, tags_json, consolidation_reason, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    ce["consolidated_episode_id"],
                    json.dumps(ce.get("source_episode_ids", []), ensure_ascii=False),
                    json.dumps(ce.get("source_event_ids", []), ensure_ascii=False),
                    ce.get("start_time"),
                    ce.get("end_time"),
                    ce.get("summary", ""),
                    json.dumps(ce.get("actors", []), ensure_ascii=False),
                    ce.get("importance_score", 0.0),
                    json.dumps(ce.get("emotional_trace", {}), ensure_ascii=False),
                    json.dumps(ce.get("tags", []), ensure_ascii=False),
                    ce.get("consolidation_reason", ""),
                    ce.get("created_at"),
                ),
            )
            conn.commit()
            return ce["consolidated_episode_id"]
        except Exception as e:
            raise RuntimeError(f"add_consolidated_episode failed: {e}")

    def list_consolidated_episodes(self) -> list[dict[str, Any]]:
        cur = self._connect().cursor()
        cur.execute("SELECT * FROM consolidated_episodes ORDER BY created_at DESC")
        return [dict(r) for r in cur.fetchall()]

    # ---------- Semantic Memory ----------
    def add_semantic_memory(self, sm: dict[str, Any]) -> str:
        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO semantic_memory
                   (memory_id, memory_type, content, source_episode_ids_json,
                    source_event_ids_json, confidence, importance, retrieval_weight,
                    decay_score, created_at, updated_at, archived)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    sm["memory_id"],
                    sm.get("memory_type", "semantic"),
                    sm.get("content", ""),
                    json.dumps(sm.get("source_episode_ids", []), ensure_ascii=False),
                    json.dumps(sm.get("source_event_ids", []), ensure_ascii=False),
                    sm.get("confidence", 0.0),
                    sm.get("importance", 0.0),
                    sm.get("retrieval_weight", 1.0),
                    sm.get("decay_score", 0.0),
                    sm.get("created_at"),
                    sm.get("updated_at"),
                    int(sm.get("archived", False)),
                ),
            )
            conn.commit()
            return sm["memory_id"]
        except Exception as e:
            raise RuntimeError(f"add_semantic_memory failed: {e}")

    def list_semantic_memory(self, active_only: bool = True) -> list[dict[str, Any]]:
        cur = self._connect().cursor()
        if active_only:
            cur.execute(
                "SELECT * FROM semantic_memory WHERE archived=0 ORDER BY created_at DESC"
            )
        else:
            cur.execute("SELECT * FROM semantic_memory ORDER BY created_at DESC")
        return [dict(r) for r in cur.fetchall()]

    # ---------- BaseStore abstract 实现 ----------
    def write(self, obj: Any) -> str:
        # 按 obj 类型分发到对应 add_*
        if obj.get("_type") == "working_memory":
            return self.add_working_memory(obj)
        if obj.get("_type") == "episode":
            return self.add_episode(obj)
        if obj.get("_type") == "reflection":
            return self.add_reflection(obj)
        raise ValueError("SQLiteStore.write: unknown _type")

    def read(self, obj_id: str) -> Any | None:
        # 遍历各表查找 id
        for tbl in ("working_memory", "episodes", "reflections"):
            cur = self._connect().cursor()
            cur.execute(f'SELECT * FROM {tbl} WHERE {"memory_id" if tbl=="working_memory" else tbl[:-1]+"_id"}=?', (obj_id,))
            r = cur.fetchone()
            if r:
                return dict(r)
        return None

    def list_all(self) -> list[Any]:
        return self.list_working_memory(active_only=False) + self.list_episodes() + self.list_reflections()

    # ---------- Plans ----------
    def add_plan(self, plan: dict[str, Any]) -> str:
        conn = self._connect()
        try:
            now = plan.get("created_at") or _utc_now()
            conn.execute(
                """INSERT INTO plans
                   (plan_id, goal_id, title, description, plan_type, status, priority,
                    evidence_ids_json, source_goal_ids_json, source_belief_ids_json,
                    source_narrative_ids_json, source_semantic_memory_ids_json,
                    source_reflection_ids_json, source_goal_progress_ids_json,
                    source_consolidated_episode_ids_json, task_ids_json, version,
                    supersedes, constitution_result_json, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    plan["plan_id"], plan.get("goal_id"), plan.get("title", ""),
                    plan.get("description", ""), plan.get("plan_type", "general"),
                    plan.get("status", "proposed"), plan.get("priority", 0.0),
                    json.dumps(plan.get("evidence_ids", []), ensure_ascii=False),
                    json.dumps(plan.get("source_goal_ids", []), ensure_ascii=False),
                    json.dumps(plan.get("source_belief_ids", []), ensure_ascii=False),
                    json.dumps(plan.get("source_narrative_ids", []), ensure_ascii=False),
                    json.dumps(plan.get("source_semantic_memory_ids", []), ensure_ascii=False),
                    json.dumps(plan.get("source_reflection_ids", []), ensure_ascii=False),
                    json.dumps(plan.get("source_goal_progress_ids", []), ensure_ascii=False),
                    json.dumps(plan.get("source_consolidated_episode_ids", []), ensure_ascii=False),
                    json.dumps(plan.get("task_ids", []), ensure_ascii=False),
                    plan.get("version", 1), plan.get("supersedes"),
                    json.dumps(plan.get("constitution_result", {}), ensure_ascii=False),
                    now, now,
                ),
            )
            conn.commit()
            return plan["plan_id"]
        except Exception as e:
            raise RuntimeError(f"add_plan failed: {e}")

    def get_plan(self, plan_id: str) -> dict[str, Any] | None:
        cur = self._connect().cursor()
        cur.execute("SELECT * FROM plans WHERE plan_id=?", (plan_id,))
        r = cur.fetchone()
        return dict(r) if r else None

    def list_plans(self, limit: int = 50) -> list[dict[str, Any]]:
        cur = self._connect().cursor()
        cur.execute("SELECT * FROM plans ORDER BY created_at DESC LIMIT ?", (limit,))
        return [dict(r) for r in cur.fetchall()]

    def list_plans_for(self, goal_id: str) -> list[dict[str, Any]]:
        cur = self._connect().cursor()
        cur.execute("SELECT * FROM plans WHERE goal_id=? ORDER BY created_at DESC", (goal_id,))
        return [dict(r) for r in cur.fetchall()]

    def get_latest_active_plan(self) -> dict[str, Any] | None:
        cur = self._connect().cursor()
        cur.execute("SELECT * FROM plans WHERE status IN ('proposed','active') "
                    "ORDER BY created_at DESC LIMIT 1")
        r = cur.fetchone()
        return dict(r) if r else None

    def update_plan_status(self, plan_id: str, status: str, reason: str = "") -> None:
        reason = (reason or "").strip()
        if not reason:
            raise ValueError("update_plan_status requires a non-empty reason (C02 explainability)")
        conn = self._connect()
        conn.execute("UPDATE plans SET status=?, updated_at=? WHERE plan_id=?",
                     (status, _utc_now(), plan_id))
        conn.commit()

    def update_plan_task_ids(self, plan_id: str, task_ids: list[str]) -> None:
        conn = self._connect()
        conn.execute("UPDATE plans SET task_ids_json=?, updated_at=? WHERE plan_id=?",
                     (json.dumps(task_ids, ensure_ascii=False), _utc_now(), plan_id))
        conn.commit()

    # ---------- Tasks ----------
    def add_task(self, task: dict[str, Any]) -> str:
        conn = self._connect()
        try:
            now = task.get("created_at") or _utc_now()
            conn.execute(
                """INSERT INTO tasks
                   (task_id, plan_id, goal_id, title, description, task_type, status,
                    order_index, priority, evidence_ids_json, depends_on_task_ids_json,
                    expected_output, execution_mode, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    task["task_id"], task.get("plan_id"), task.get("goal_id"),
                    task.get("title", ""), task.get("description", ""),
                    task.get("task_type", "general"), task.get("status", "proposed"),
                    task.get("order_index", 0), task.get("priority", 0.0),
                    json.dumps(task.get("evidence_ids", []), ensure_ascii=False),
                    json.dumps(task.get("depends_on_task_ids", []), ensure_ascii=False),
                    task.get("expected_output", ""),
                    task.get("execution_mode", "manual_only"),
                    now, now,
                ),
            )
            conn.commit()
            return task["task_id"]
        except Exception as e:
            raise RuntimeError(f"add_task failed: {e}")

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        cur = self._connect().cursor()
        cur.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,))
        r = cur.fetchone()
        return dict(r) if r else None

    def list_tasks(self, limit: int = 100) -> list[dict[str, Any]]:
        cur = self._connect().cursor()
        cur.execute("SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,))
        return [dict(r) for r in cur.fetchall()]

    def list_tasks_for_plan(self, plan_id: str) -> list[dict[str, Any]]:
        cur = self._connect().cursor()
        cur.execute("SELECT * FROM tasks WHERE plan_id=? ORDER BY order_index ASC", (plan_id,))
        return [dict(r) for r in cur.fetchall()]

    def update_task_status(self, task_id: str, status: str, reason: str = "") -> None:
        reason = (reason or "").strip()
        if not reason:
            raise ValueError("update_task_status requires a non-empty reason (C02 explainability)")
        conn = self._connect()
        conn.execute("UPDATE tasks SET status=?, updated_at=? WHERE task_id=?",
                     (status, _utc_now(), task_id))
        conn.commit()

    # ---------- Decisions ----------
    def add_decision(self, dec: dict[str, Any]) -> str:
        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO decisions
                   (decision_id, decision_type, status, selected_goal_id, selected_plan_id,
                    selected_task_id, selected_task_title, reason, decision_factors_json,
                    evidence_ids_json, source_goal_ids_json, source_plan_ids_json,
                    source_task_ids_json, source_belief_ids_json, source_narrative_ids_json,
                    source_semantic_memory_ids_json, source_goal_progress_ids_json,
                    manual_review_required, execution_allowed, constitution_result_json,
                    related_long_term_goal_ids_json, related_motivation_ids_json, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    dec["decision_id"], dec.get("decision_type", "general"),
                    dec.get("status", "waiting_for_review"),
                    dec.get("selected_goal_id"), dec.get("selected_plan_id"),
                    dec.get("selected_task_id"), dec.get("selected_task_title", ""),
                    dec.get("reason", ""),
                    json.dumps(dec.get("decision_factors", {}), ensure_ascii=False),
                    json.dumps(dec.get("evidence_ids", []), ensure_ascii=False),
                    json.dumps(dec.get("source_goal_ids", []), ensure_ascii=False),
                    json.dumps(dec.get("source_plan_ids", []), ensure_ascii=False),
                    json.dumps(dec.get("source_task_ids", []), ensure_ascii=False),
                    json.dumps(dec.get("source_belief_ids", []), ensure_ascii=False),
                    json.dumps(dec.get("source_narrative_ids", []), ensure_ascii=False),
                    json.dumps(dec.get("source_semantic_memory_ids", []), ensure_ascii=False),
                    json.dumps(dec.get("source_goal_progress_ids", []), ensure_ascii=False),
                    int(dec.get("manual_review_required", True)),
                    int(dec.get("execution_allowed", False)),
                    json.dumps(dec.get("constitution_result", {}), ensure_ascii=False),
                    json.dumps(dec.get("related_long_term_goal_ids", []), ensure_ascii=False),
                    json.dumps(dec.get("related_motivation_ids", []), ensure_ascii=False),
                    dec.get("created_at") or _utc_now(),
                ),
            )
            conn.commit()
            return dec["decision_id"]
        except Exception as e:
            raise RuntimeError(f"add_decision failed: {e}")

    def get_decision(self, decision_id: str) -> dict[str, Any] | None:
        cur = self._connect().cursor()
        cur.execute("SELECT * FROM decisions WHERE decision_id=?", (decision_id,))
        r = cur.fetchone()
        return dict(r) if r else None

    def list_decisions(self, limit: int = 50) -> list[dict[str, Any]]:
        cur = self._connect().cursor()
        cur.execute("SELECT * FROM decisions ORDER BY created_at DESC LIMIT ?", (limit,))
        return [dict(r) for r in cur.fetchall()]

    def get_latest_waiting_decision(self) -> dict[str, Any] | None:
        cur = self._connect().cursor()
        cur.execute("SELECT * FROM decisions WHERE status='waiting_for_review' "
                    "ORDER BY created_at DESC LIMIT 1")
        r = cur.fetchone()
        return dict(r) if r else None

    # ---------- Long-term Goals ----------
    def add_long_term_goal(self, g: dict[str, Any]) -> str:
        conn = self._connect()
        try:
            now = g.get("created_at") or _utc_now()
            conn.execute(
                """INSERT INTO long_term_goals
                   (long_term_goal_id, title, description, goal_type, status, priority,
                    progress_value, evidence_ids_json, source_goal_ids_json,
                    source_belief_ids_json, source_narrative_ids_json,
                    source_semantic_memory_ids_json, source_reflection_ids_json,
                    source_decision_ids_json, continuity_reason, version, supersedes,
                    constitution_result_json, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    g["long_term_goal_id"], g.get("title", ""), g.get("description", ""),
                    g.get("goal_type", "general"), g.get("status", "active"),
                    g.get("priority", 0.0), g.get("progress_value", 0.0),
                    json.dumps(g.get("evidence_ids", []), ensure_ascii=False),
                    json.dumps(g.get("source_goal_ids", []), ensure_ascii=False),
                    json.dumps(g.get("source_belief_ids", []), ensure_ascii=False),
                    json.dumps(g.get("source_narrative_ids", []), ensure_ascii=False),
                    json.dumps(g.get("source_semantic_memory_ids", []), ensure_ascii=False),
                    json.dumps(g.get("source_reflection_ids", []), ensure_ascii=False),
                    json.dumps(g.get("source_decision_ids", []), ensure_ascii=False),
                    g.get("continuity_reason", ""),
                    g.get("version", 1), g.get("supersedes"),
                    json.dumps(g.get("constitution_result", {}), ensure_ascii=False),
                    now, now,
                ),
            )
            conn.commit()
            return g["long_term_goal_id"]
        except Exception as e:
            raise RuntimeError(f"add_long_term_goal failed: {e}")

    def list_long_term_goals(self, limit: int = 50) -> list[dict[str, Any]]:
        cur = self._connect().cursor()
        cur.execute("SELECT * FROM long_term_goals ORDER BY created_at DESC LIMIT ?", (limit,))
        return [_restore_ltg(dict(r)) for r in cur.fetchall()]

    def get_long_term_goal(self, goal_id: str) -> dict[str, Any] | None:
        cur = self._connect().cursor()
        cur.execute("SELECT * FROM long_term_goals WHERE long_term_goal_id=?", (goal_id,))
        r = cur.fetchone()
        return _restore_ltg(dict(r)) if r else None

    def list_active_long_term_goals(self) -> list[dict[str, Any]]:
        cur = self._connect().cursor()
        cur.execute("SELECT * FROM long_term_goals WHERE status IN ('active','completed_candidate') "
                    "ORDER BY priority DESC, created_at DESC")
        return [dict(r) for r in cur.fetchall()]

    # ---------- Goal Consolidations ----------
    def add_goal_consolidation(self, c: dict[str, Any]) -> str:
        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO goal_consolidations
                   (consolidation_id, long_term_goal_id, source_goal_ids_json,
                    consolidation_type, reason, evidence_ids_json, source_progress_ids_json,
                    source_decision_ids_json, action_taken, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    c["consolidation_id"], c.get("long_term_goal_id"),
                    json.dumps(c.get("source_goal_ids", []), ensure_ascii=False),
                    c.get("consolidation_type", "general"), c.get("reason", ""),
                    json.dumps(c.get("evidence_ids", []), ensure_ascii=False),
                    json.dumps(c.get("source_progress_ids", []), ensure_ascii=False),
                    json.dumps(c.get("source_decision_ids", []), ensure_ascii=False),
                    c.get("action_taken", "linked_only"), c.get("created_at") or _utc_now(),
                ),
            )
            conn.commit()
            return c["consolidation_id"]
        except Exception as e:
            raise RuntimeError(f"add_goal_consolidation failed: {e}")

    def list_goal_consolidations(self, limit: int = 50) -> list[dict[str, Any]]:
        cur = self._connect().cursor()
        cur.execute("SELECT * FROM goal_consolidations ORDER BY created_at DESC LIMIT ?", (limit,))
        return [_restore_cons(dict(r)) for r in cur.fetchall()]

    # ---------- Motivations ----------
    def add_motivation(self, m: dict[str, Any]) -> str:
        conn = self._connect()
        try:
            now = m.get("created_at") or _utc_now()
            conn.execute(
                """INSERT INTO motivations
                   (motivation_id, motivation_type, status, direction, reason,
                    motivation_score, priority, evidence_ids_json,
                    source_long_term_goal_ids_json, source_goal_ids_json,
                    source_belief_ids_json, source_narrative_ids_json,
                    source_semantic_memory_ids_json, source_reflection_ids_json,
                    source_decision_ids_json, source_goal_progress_ids_json,
                    manual_review_required, execution_allowed,
                    version, supersedes, constitution_result_json, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    m["motivation_id"], m.get("motivation_type", "general"),
                    m.get("status", "active"), m.get("direction", ""), m.get("reason", ""),
                    m.get("motivation_score", 0.0), m.get("priority", 0.0),
                    json.dumps(m.get("evidence_ids", []), ensure_ascii=False),
                    json.dumps(m.get("source_long_term_goal_ids", []), ensure_ascii=False),
                    json.dumps(m.get("source_goal_ids", []), ensure_ascii=False),
                    json.dumps(m.get("source_belief_ids", []), ensure_ascii=False),
                    json.dumps(m.get("source_narrative_ids", []), ensure_ascii=False),
                    json.dumps(m.get("source_semantic_memory_ids", []), ensure_ascii=False),
                    json.dumps(m.get("source_reflection_ids", []), ensure_ascii=False),
                    json.dumps(m.get("source_decision_ids", []), ensure_ascii=False),
                    json.dumps(m.get("source_goal_progress_ids", []), ensure_ascii=False),
                    1 if m.get("manual_review_required", True) else 0,
                    1 if m.get("execution_allowed", False) else 0,
                    m.get("version", 1), m.get("supersedes"),
                    json.dumps(m.get("constitution_result", {}), ensure_ascii=False),
                    now, now,
                ),
            )
            conn.commit()
            return m["motivation_id"]
        except Exception as e:
            raise RuntimeError(f"add_motivation failed: {e}")

    def list_motivations(self, limit: int = 50) -> list[dict[str, Any]]:
        cur = self._connect().cursor()
        cur.execute("SELECT * FROM motivations ORDER BY created_at DESC LIMIT ?", (limit,))
        return [_restore_mot(dict(r)) for r in cur.fetchall()]

    def get_motivation(self, motivation_id: str) -> dict[str, Any] | None:
        cur = self._connect().cursor()
        cur.execute("SELECT * FROM motivations WHERE motivation_id=?", (motivation_id,))
        r = cur.fetchone()
        return _restore_mot(dict(r)) if r else None

    def list_active_motivations(self) -> list[dict[str, Any]]:
        cur = self._connect().cursor()
        cur.execute("SELECT * FROM motivations WHERE status IN ('active','suspended') "
                    "ORDER BY priority DESC, created_at DESC")
        return [_restore_mot(dict(r)) for r in cur.fetchall()]

    # ---------- Action Registry ----------
    def init_action_registry(self, actions: list[dict[str, Any]]) -> None:
        """幂等初始化 action_registry 默认白名单（已存在动作跳过，避免覆盖启用状态）。"""
        conn = self._connect()
        now = _utc_now()
        try:
            for a in actions:
                cur = conn.execute("SELECT COUNT(*) FROM action_registry WHERE action_name=?",
                                   (a["action_name"],))
                if cur.fetchone()[0] == 0:
                    conn.execute(
                        """INSERT INTO action_registry
                           (action_name, action_level, description, enabled,
                            allowed_scope, daily_limit, requires_approval, banned,
                            created_at, updated_at)
                           VALUES (?,?,?,?,?,?,?,?,?,?)""",
                        (
                            a["action_name"], a.get("action_level", "L∞"),
                            a.get("description", ""),
                            1 if a.get("enabled", True) else 0,
                            a.get("allowed_scope", ""),
                            a.get("daily_limit", 0),
                            1 if a.get("requires_approval", False) else 0,
                            1 if a.get("banned", False) else 0,
                            now, now,
                        ),
                    )
            conn.commit()
        except Exception as e:
            raise RuntimeError(f"init_action_registry failed: {e}")

    def get_action(self, action_name: str) -> dict[str, Any] | None:
        cur = self._connect().cursor()
        cur.execute("SELECT * FROM action_registry WHERE action_name=?", (action_name,))
        r = cur.fetchone()
        return _restore_reg(dict(r)) if r else None

    def list_action_registry(self) -> list[dict[str, Any]]:
        cur = self._connect().cursor()
        cur.execute("SELECT * FROM action_registry ORDER BY action_level, action_name")
        return [_restore_reg(dict(r)) for r in cur.fetchall()]

    # ---------- Execution Requests ----------
    def add_execution_request(self, er: dict[str, Any]) -> str:
        conn = self._connect()
        try:
            now = er.get("created_at") or _utc_now()
            conn.execute(
                """INSERT INTO execution_requests
                   (execution_request_id, decision_id, selected_goal_id,
                    selected_plan_id, selected_task_id, action_name, action_level,
                    status, approval_required, manual_review_required,
                    execution_allowed, reason, request_payload_json,
                    evidence_ids_json, source_goal_ids_json, source_plan_ids_json,
                    source_task_ids_json, source_decision_ids_json,
                    risk_factors_json, gate_result_json, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    er["execution_request_id"], er.get("decision_id"),
                    er.get("selected_goal_id"), er.get("selected_plan_id"),
                    er.get("selected_task_id"), er.get("action_name", ""),
                    er.get("action_level", "L0"),
                    er.get("status", "proposed"),
                    1 if er.get("approval_required", False) else 0,
                    1 if er.get("manual_review_required", False) else 0,
                    1 if er.get("execution_allowed", False) else 0,
                    er.get("reason", ""),
                    json.dumps(er.get("request_payload", {}), ensure_ascii=False),
                    json.dumps(er.get("evidence_ids", []), ensure_ascii=False),
                    json.dumps(er.get("source_goal_ids", []), ensure_ascii=False),
                    json.dumps(er.get("source_plan_ids", []), ensure_ascii=False),
                    json.dumps(er.get("source_task_ids", []), ensure_ascii=False),
                    json.dumps(er.get("source_decision_ids", []), ensure_ascii=False),
                    json.dumps(er.get("risk_factors", {}), ensure_ascii=False),
                    json.dumps(er.get("gate_result", {}), ensure_ascii=False),
                    now, now,
                ),
            )
            conn.commit()
            return er["execution_request_id"]
        except Exception as e:
            raise RuntimeError(f"add_execution_request failed: {e}")

    def get_execution_request(self, execution_request_id: str) -> dict[str, Any] | None:
        cur = self._connect().cursor()
        cur.execute("SELECT * FROM execution_requests WHERE execution_request_id=?",
                    (execution_request_id,))
        r = cur.fetchone()
        return _restore_exec(dict(r)) if r else None

    def list_execution_requests(self, limit: int = 100,
                                status: str | None = None) -> list[dict[str, Any]]:
        cur = self._connect().cursor()
        if status:
            cur.execute("SELECT * FROM execution_requests WHERE status=? "
                        "ORDER BY created_at DESC LIMIT ?", (status, limit))
        else:
            cur.execute("SELECT * FROM execution_requests ORDER BY created_at DESC LIMIT ?",
                        (limit,))
        return [_restore_exec(dict(r)) for r in cur.fetchall()]

    def update_execution_request(self, execution_request_id: str,
                                 **fields: Any) -> None:
        """按需更新 execution_requests 行（如 status / execution_allowed / gate_result）。"""
        conn = self._connect()
        if not fields:
            return
        sets = []
        vals: list[Any] = []
        for k, v in fields.items():
            col = k
            if k in ("gate_result",):
                col = "gate_result_json"
                v = json.dumps(v, ensure_ascii=False)
            elif k in ("request_payload",):
                col = "request_payload_json"
                v = json.dumps(v, ensure_ascii=False)
            elif k in ("risk_factors",):
                col = "risk_factors_json"
                v = json.dumps(v, ensure_ascii=False)
            elif k in ("evidence_ids", "source_goal_ids", "source_plan_ids",
                       "source_task_ids", "source_decision_ids"):
                col = f"{k}_json"
                v = json.dumps(v, ensure_ascii=False)
            elif k in ("approval_required", "manual_review_required", "execution_allowed"):
                v = 1 if v else 0
            sets.append(f"{col}=?")
            vals.append(v)
        vals.append(_utc_now())
        sets.append("updated_at=?")
        conn.execute(
            f"UPDATE execution_requests SET {', '.join(sets)} "
            "WHERE execution_request_id=?",
            (*vals, execution_request_id),
        )
        conn.commit()

    # ---------- Execution Approvals ----------
    def add_approval(self, ap: dict[str, Any]) -> str:
        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO execution_approvals
                   (approval_id, execution_request_id, reviewer,
                    approval_decision, reason, created_at)
                   VALUES (?,?,?,?,?,?)""",
                (
                    ap["approval_id"], ap["execution_request_id"],
                    ap.get("reviewer", "human"), ap.get("approval_decision", "approved"),
                    ap.get("reason", ""), ap.get("created_at") or _utc_now(),
                ),
            )
            conn.commit()
            return ap["approval_id"]
        except Exception as e:
            raise RuntimeError(f"add_approval failed: {e}")

    def list_approvals(self, execution_request_id: str | None = None,
                       limit: int = 100) -> list[dict[str, Any]]:
        cur = self._connect().cursor()
        if execution_request_id:
            cur.execute("SELECT * FROM execution_approvals WHERE execution_request_id=? "
                        "ORDER BY created_at DESC LIMIT ?", (execution_request_id, limit))
        else:
            cur.execute("SELECT * FROM execution_approvals ORDER BY created_at DESC LIMIT ?",
                        (limit,))
        return [dict(r) for r in cur.fetchall()]

    # ---------- Action Logs ----------
    def add_action_log(self, log: dict[str, Any]) -> str:
        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO action_logs
                   (action_log_id, execution_request_id, action_name, action_level,
                    status, input_payload_json, output_payload_json,
                    result_summary, result_evidence_id, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    log["action_log_id"], log.get("execution_request_id"),
                    log.get("action_name", ""), log.get("action_level", "L0"),
                    log.get("status", "executed"),
                    json.dumps(log.get("input_payload", {}), ensure_ascii=False),
                    json.dumps(log.get("output_payload", {}), ensure_ascii=False),
                    log.get("result_summary", ""), log.get("result_evidence_id"),
                    log.get("created_at") or _utc_now(),
                ),
            )
            conn.commit()
            return log["action_log_id"]
        except Exception as e:
            raise RuntimeError(f"add_action_log failed: {e}")

    def list_action_logs(self, limit: int = 100) -> list[dict[str, Any]]:
        cur = self._connect().cursor()
        cur.execute("SELECT * FROM action_logs ORDER BY created_at DESC LIMIT ?", (limit,))
        return [_restore_log(dict(r)) for r in cur.fetchall()]

    # ---------- Work Items (Phase 15A Feed Layer) ----------
    def add_work_item(self, wi: dict[str, Any]) -> str:
        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO work_items
                   (work_item_id, source, source_id, work_type, title, description,
                    priority_hint, related_goal_ids_json, related_plan_ids_json,
                    evidence_ids_json, status, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    wi["work_item_id"], wi.get("source"), wi.get("source_id"),
                    wi.get("work_type"), wi.get("title"), wi.get("description"),
                    wi.get("priority_hint"),
                    json.dumps(wi.get("related_goal_ids", []), ensure_ascii=False),
                    json.dumps(wi.get("related_plan_ids", []), ensure_ascii=False),
                    json.dumps(wi.get("evidence_ids", []), ensure_ascii=False),
                    wi.get("status", "new"),
                    wi.get("created_at") or _utc_now(),
                ),
            )
            conn.commit()
            return wi["work_item_id"]
        except Exception as e:
            raise RuntimeError(f"add_work_item failed: {e}")

    def get_work_item(self, work_item_id: str) -> dict[str, Any] | None:
        cur = self._connect().cursor()
        cur.execute("SELECT * FROM work_items WHERE work_item_id=?", (work_item_id,))
        r = cur.fetchone()
        return _restore_log(dict(r)) if r else None

    def list_work_items(self, status: str | None = None,
                        limit: int = 100) -> list[dict[str, Any]]:
        cur = self._connect().cursor()
        if status:
            cur.execute("SELECT * FROM work_items WHERE status=? "
                        "ORDER BY created_at DESC LIMIT ?", (status, limit))
        else:
            cur.execute("SELECT * FROM work_items ORDER BY created_at DESC LIMIT ?", (limit,))
        return [_restore_log(dict(r)) for r in cur.fetchall()]

    def update_work_item_status(self, work_item_id: str, status: str) -> None:
        conn = self._connect()
        conn.execute("UPDATE work_items SET status=? WHERE work_item_id=?",
                     (status, work_item_id))
        conn.commit()

    # ---------- Action Candidates (Phase 15A Feed Layer) ----------
    def add_action_candidate(self, cand: dict[str, Any]) -> str:
        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO action_candidates
                   (candidate_id, work_item_id, action_name, action_level,
                    payload_json, risk_factors_json, evidence_ids_json,
                    source, status, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    cand["candidate_id"], cand.get("work_item_id"),
                    cand.get("action_name", ""), cand.get("action_level", "L0"),
                    json.dumps(cand.get("payload", {}), ensure_ascii=False),
                    json.dumps(cand.get("risk_factors", {}), ensure_ascii=False),
                    json.dumps(cand.get("evidence_ids", []), ensure_ascii=False),
                    cand.get("source"), cand.get("status", "pending_gate"),
                    cand.get("created_at") or _utc_now(),
                ),
            )
            conn.commit()
            return cand["candidate_id"]
        except Exception as e:
            raise RuntimeError(f"add_action_candidate failed: {e}")

    def get_action_candidate(self, candidate_id: str) -> dict[str, Any] | None:
        cur = self._connect().cursor()
        cur.execute("SELECT * FROM action_candidates WHERE candidate_id=?", (candidate_id,))
        r = cur.fetchone()
        return _restore_log(dict(r)) if r else None

    def list_action_candidates(self, status: str | None = None,
                               limit: int = 100) -> list[dict[str, Any]]:
        cur = self._connect().cursor()
        if status:
            cur.execute("SELECT * FROM action_candidates WHERE status=? "
                        "ORDER BY created_at DESC LIMIT ?", (status, limit))
        else:
            cur.execute("SELECT * FROM action_candidates ORDER BY created_at DESC LIMIT ?",
                        (limit,))
        return [_restore_log(dict(r)) for r in cur.fetchall()]

    def update_action_candidate_status(self, candidate_id: str, status: str) -> None:
        conn = self._connect()
        conn.execute("UPDATE action_candidates SET status=? WHERE candidate_id=?",
                     (status, candidate_id))
        conn.commit()
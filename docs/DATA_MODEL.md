# DATA MODEL

Project Soul 的核心数据结构。实现于 `soul/schemas/`（当前为 dataclass 占位，无校验逻辑）。

## 存储总览

| 介质 | 用途 |
|---|---|
| **JSONL** | 不可变 evidence log（只追加，chain hash 防篡改） |
| **SQLite** | 结构化状态：episodes / memory / beliefs / relationships / goals / narratives / self_snapshots |
| **Markdown** | constitution、narrative、可读摘要 |
| 向量库 | 可选，仅日后语义检索时引入（本阶段不用） |

数据分层：`data/{evidence,episodes,memory,narratives,beliefs,relationships,self_snapshots}/`。

## 8 类结构

### 1. Event / Evidence（不可变事实层）
```
event_id, timestamp, source, actor, event_type,
raw_content, normalized_content, metadata,
hash, previous_hash, created_at
```
- 只允许追加；`hash` = hash(本体+previous_hash) 链式防止篡改。

### 2. Episode（多 event 组成的经历片段）
```
episode_id, start_time, end_time, summary,
event_ids, actors, outcome, importance_score,
emotional_trace, tags
```

### 3. Memory（分层保存）
```
memory_id, memory_type, content, source_episode_ids,
confidence, importance, retrieval_weight, decay_score,
created_at, updated_at, archived
```
- memory_type ∈ {working, episode, semantic, relationship, core, archive}

### 4. Belief
```
belief_id, statement, confidence, evidence_ids,
supporting_episode_ids, contradiction_ids,
version, created_at, updated_at
```

### 5. Relationship
```
person_id, name, trust, familiarity,
importance, affinity, shared_goals, conflict_history,
evidence_ids, last_interaction_at, version
```

### 6. Narrative
```
narrative_id, title, narrative_type, content,
meaning, identity_effect, evidence_ids, episode_ids,
version, supersedes, created_at
```
- `supersedes` 指向被替代的旧版本；旧版本不删除，只归档。

### 7. Goal
```
goal_id, title, source, priority, status,
reason, related_beliefs, related_relationships,
created_at, updated_at
```

### 8. Self Snapshot
```
snapshot_id, timestamp, identity_summary,
active_beliefs, active_relationships, active_goals,
dominant_narratives, current_emotion_state,
change_log, evidence_refs, version
```

## Evidence Layer 与 Narrative Layer 边界

```
Reality Layer(证据层)     记录"发生了什么"。只允许 APPEND。
Narrative Layer(叙事层)   解释"它意味着什么"。可版本更新，但必须引用 evidence_id。
```
旧 narrative 不删除，只归档（supersedes 指针）。叙事内容若含证据层不存在的事实 → Constitution 拒绝。

## Phase 10：Plans / Tasks 表

```sql
CREATE TABLE plans (
  plan_id TEXT PRIMARY KEY,
  goal_id TEXT,                 -- 必须引用 active goal
  title / description TEXT,
  plan_type TEXT,               -- implementation/verification/safety/maintenance/research/consolidation/general
  status TEXT,                  -- proposed/active/suspended/completed_candidate/completed/rejected/superseded
  priority REAL,                -- 0.0-1.0
  evidence_ids_json JSON,       -- 必须引用已存在 evidence
  source_goal_ids_json / source_belief_ids_json / source_narrative_ids_json
  / source_semantic_memory_ids_json / source_reflection_ids_json
  / source_goal_progress_ids_json JSON,   -- 至少一类 source
  task_ids_json JSON, version INTEGER, supersedes TEXT,
  constitution_result_json JSON, created_at, updated_at
);
CREATE TABLE tasks (
  task_id TEXT PRIMARY KEY,
  plan_id TEXT, goal_id TEXT,   -- 必须引用存在 plan + active goal
  title / description TEXT,
  task_type TEXT,               -- inspect/implement/verify/document/review/maintain/research/general
  status TEXT,                  -- proposed/ready/blocked/in_progress_candidate/completed_candidate/rejected
  order_index INTEGER, priority REAL,
  evidence_ids_json JSON,
  depends_on_task_ids_json JSON,   -- 顺序依赖，不自动推进
  expected_output TEXT,
  execution_mode TEXT,          -- manual_only(默认) / future_decision_required
  created_at, updated_at
);
```

约束：plan 不自动 completed；task 默认 proposed + manual_only；都不是 execution command。

## Phase 11：decisions 表

```sql
CREATE TABLE decisions (
  decision_id TEXT PRIMARY KEY,
  decision_type TEXT,    -- next_task_recommendation/defer/review_required/blocked/general
  status TEXT,           -- proposed/waiting_for_review/rejected/superseded
  selected_goal_id / selected_plan_id / selected_task_id TEXT,
  selected_task_title TEXT,
  reason TEXT,           -- 中性工程描述，禁拟人化
  decision_factors_json JSON,     -- goal_priority/progress/plan_status/task_status/dependency/evidence_strength...
  evidence_ids_json JSON,
  source_goal_ids_json / source_plan_ids_json / source_task_ids_json
  / source_belief_ids_json / source_narrative_ids_json / source_semantic_memory_ids_json
  / source_goal_progress_ids_json JSON,
  manual_review_required INTEGER, -- 必须 1
  execution_allowed INTEGER,      -- 必须 0
  constitution_result_json JSON, created_at TEXT
);
```

约束：decision 必须引用 existing goal_id/plan_id/task_id（defer/blocked 豁免 task_id）+ evidence_ids；manual_review_required=true、execution_allowed=false；不自动改 task/plan/goal status；不执行外部动作。Phase 12 起 decisions 表有可选列 `related_long_term_goal_ids_json`（只读关联，Decision 逻辑不改）。

## Phase 12：long_term_goals / goal_consolidations 表

```sql
CREATE TABLE long_term_goals (
  long_term_goal_id TEXT PRIMARY KEY,
  title / description TEXT,
  goal_type TEXT,       -- project_continuity/safety_continuity/verification_continuity/
                        --   architecture_continuity/maintenance_continuity/research_continuity/general
  status TEXT,          -- active/suspended/completed_candidate/rejected/superseded（禁自动 completed）
  priority REAL,        -- 0.0-1.0，由 source goals 最新 progress 加权聚合
  progress_value REAL,  -- 0.0-1.0，加权平均（source completed 权重折半，单次 delta 上限 0.5）
  evidence_ids_json JSON,                  -- 聚合自 source goals 的 evidence，必须真实存在
  source_goal_ids_json / source_belief_ids_json / source_narrative_ids_json
  / source_semantic_memory_ids_json / source_reflection_ids_json / source_decision_ids_json JSON,
  continuity_reason TEXT,  -- 命中哪条连续性规则 + 为何归并
  version INTEGER, supersedes TEXT,        -- 旧版本不删，用 supersedes 指针
  constitution_result_json JSON, created_at, updated_at
);
CREATE TABLE goal_consolidations (
  consolidation_id TEXT PRIMARY KEY,
  long_term_goal_id TEXT,     -- 指向新建的 parent
  source_goal_ids_json JSON,  -- 必须引用存在的 source goals
  consolidation_type TEXT,    -- same_phase_direction/same_safety_boundary/same_verification_chain/
                              --   same_maintenance_area/same_architecture_thread/duplicate_or_overlap/general
  reason TEXT,                -- 中性工程描述，禁拟人化
  evidence_ids_json JSON,
  source_progress_ids_json / source_decision_ids_json JSON,
  action_taken TEXT,          -- linked_only/parent_created/supersedes_suggested/no_status_change（禁 delete）
  created_at TEXT
);
-- decisions 迁移：ALTER TABLE decisions ADD COLUMN related_long_term_goal_ids_json JSON（可选，Phase 12 init_schema 自动补）
```

约束：**MVP 不用 LLM**，规则式（project_phase / safety / verification / maintenance 四方向关键词分组）；长目标须 **≥2 source goals**（safety_continuity 例外）；evidence 必引且真实存在；**不自动 completed、不得 delete / 覆盖 source goals**（action_taken 禁 delete，旧版本用 supersedes）；progress/priority 越界即 reject。

## Phase 13：motivations 表

```sql
CREATE TABLE motivations (
  motivation_id TEXT PRIMARY KEY,
  motivation_type TEXT,    -- project_continuity/safety_boundary/verification_traceability/
                           --   maintenance_continuity/architecture_development/research_direction/general
  status TEXT,             -- active/suspended/rejected/superseded
  direction TEXT,          -- 中性方向描述（禁自主欲望/绝对化词）
  reason TEXT,             -- 解释为什么该方向值得继续关注；写明 score 来源
  motivation_score REAL,   -- 0.0-1.0，6 因子加权
  priority REAL,           -- 0.0-1.0
  evidence_ids_json JSON,  -- 必须引用真实存在 evidence
  source_long_term_goal_ids_json / source_goal_ids_json / source_belief_ids_json
  / source_narrative_ids_json / source_semantic_memory_ids_json / source_reflection_ids_json
  / source_decision_ids_json / source_goal_progress_ids_json JSON,
                           -- 至少引用一类来源
  manual_review_required INTEGER,  -- 必须 1
  execution_allowed INTEGER,      -- 必须 0
  version INTEGER, supersedes TEXT,
  constitution_result_json JSON, created_at, updated_at
);
-- decisions 迁移：ALTER TABLE decisions ADD COLUMN related_motivation_ids_json JSON（可选，Phase 13 init_schema 自动补）
```

约束：**MVP 不用 LLM**；一条 motivation 代表一个"值得持续关注的方向"，引用 evidence + 至少一类 source；score / priority ∈[0,1]；`manual_review_required=true`、`execution_allowed=false`；**不创建 goal/plan/task、不改任何状态、不执行**；旧版本用 supersedes 不删除；direction/reason 禁自主欲望词（我想要/我必须/永远/唯一/立即执行/调用API/发送邮件等）；低证据不可给高 certainty。

## Phase 14：action_registry / execution_requests / execution_approvals / action_logs 表

```sql
CREATE TABLE action_registry (
  action_name TEXT PRIMARY KEY,
  action_level TEXT,            -- L0/L1/L2/L∞
  description TEXT,
  enabled INTEGER,              -- 只有 enabled=true 才可进 Gate
  allowed_scope TEXT,           -- internal/external/none
  daily_limit INTEGER,          -- 0=不限
  requires_approval INTEGER,
  banned INTEGER,               -- banned=true 直接 reject
  created_at, updated_at
);

CREATE TABLE execution_requests (
  execution_request_id TEXT PRIMARY KEY,
  decision_id TEXT,             -- 必须引用真实 decision
  selected_goal_id / selected_plan_id / selected_task_id TEXT,
  action_name TEXT, action_level TEXT,
  status TEXT,                  -- proposed/auto_allowed/waiting_for_approval/approved/rejected/blocked/executed/failed
  approval_required INTEGER, manual_review_required INTEGER,
  execution_allowed INTEGER,    -- 只能由 Permission Gate 裁决，绝不来自 Decision
  reason TEXT, request_payload_json JSON,
  evidence_ids_json / source_goal_ids_json / source_plan_ids_json
  / source_task_ids_json / source_decision_ids_json JSON,
  risk_factors_json / gate_result_json JSON,
  created_at, updated_at
);

CREATE TABLE execution_approvals (
  approval_id TEXT PRIMARY KEY,
  execution_request_id TEXT,
  reviewer TEXT,                -- human
  approval_decision TEXT,       -- approved/rejected
  reason TEXT,                  -- 必须非空
  created_at
);

CREATE TABLE action_logs (
  action_log_id TEXT PRIMARY KEY,
  execution_request_id TEXT, action_name TEXT, action_level TEXT,
  status TEXT,                  -- executed/failed
  input_payload_json / output_payload_json JSON,
  result_summary TEXT, result_evidence_id TEXT,  -- 指向 action_result evidence
  created_at
);
```

约束：4 张表都 `CREATE TABLE IF NOT EXISTS` 不破坏 Phase 1-13 数据、不做复杂 migration；JSON 统一 json.dumps、时间 UTC ISO；execution/approval/action logs **不删除**；rejected execution 写 constitution_rejections；每次 sandbox action 必须写 action_log 且把执行结果追加为新 `action_result` evidence，`result_evidence_id` 指向它；Gates 只读不改 goal/plan/task/decision 状态。
# Project Soul / Soul Factory

一个多 Agent 协作的 **认知工厂**：研究一个 AI Agent 如何通过 经历 → 记忆 → 信念 → 关系 → 叙事 → 目标 → 反思 的持续运行，逐步形成稳定的**自我模型（self-model）**。

> **边界声明**：本系统**不主张、不隐含、不暗示** AI 拥有意识或灵魂。它建模的是**可解释、可回滚、可审计的状态演化**，不是“主观体验”。任何输出都应能回答“我是如何变成现在这样的”。

## 核心公式

```
Current Self
+ Experience
+ Perception
+ Emotion
+ Memory
+ Belief
+ Relationship
+ Narrative
+ Goal
+ Reflection
= Next Self
```

约束：整个过程受 **Soul Constitution** 约束（见 `docs/SAFETY_AND_CONSTITUTION.md` 与 `soul/constitution/constitution.md`）。

## 目录结构

```
Project Soul/
├── soul/               # Python 包
│   ├── constitution/   # 宪法（Markdown）
│   ├── schemas/        # 8 类数据结构（dataclass，零逻辑）
│   ├── agents/         # 15 个 Agent（MVP 用 9 个，其余为预留 stub）
│   ├── storage/        # 存储接口（evidence JSONL / SQLite / importer 占位）
│   ├── loops/          # Fast Loop / Slow Loop（骨架）
│   ├── runtime/        # 运行时上下文（占位）
│   ├── tests/          # 测试
│   ├── cli.py          # 最小 CLI
│   └── __main__.py
├── data/               # 分层持久化（每层一个子目录）
│   ├── evidence/       #  不可变证据（JSONL，只追加）
│   ├── episodes/
│   ├── memory/
│   ├── narratives/
│   ├── beliefs/
│   ├── relationships/
│   └── self_snapshots/
├── docs/               # 架构 / 路线 / 数据模型 / 安全宪法
├── requirements.txt
├── .gitignore
└── README.md
```

## 快速开始（Phase 1-12）

项目当前已完成 **Phase 1-12**：
- Phase 1 骨架（agents/stores/loops 契约）
- Phase 2 证据链（evidence JSONL + hash chain 防篡改）
- Phase 3 Memory Agent 落库（working/episode/short reflection，SQLite）
- Phase 4 Slow Loop v0（episode 聚合 → semantic memory → long reflection）
- Phase 5 Narrative Engine + Constitution Agent 校验

运行时**无 LLM、无 API**，全部规则式（规则可解释、可审计）。

```bash
cd "C:/Users/w/Documents/ChatGPT/Project Soul"
python -m soul          # 期望输出: Project Soul skeleton ready
pytest soul/tests/      # 期望全过

# 全链路命令（Phase 2-5）
python -m soul feed "<消息>" [--json]      # full pipeline trace
python -m soul verify-evidence             # 校验 evidence hash chain
python -m soul list-working-memory         # 短期记忆
python -m soul list-episodes               # 经历片段
python -m soul list-reflections            # 短反思
python -m soul run-slow-loop               # Slow Loop（聚合→semantic→long reflection）
python -m soul list-semantic-memory        # 语义记忆
python -m soul list-consolidated-episodes  # 聚合经历
python -m soul list-long-reflections       # 长反思
python -m soul run-narrative-cycle         # Narrative cycle（生成+宪法校验）
python -m soul list-narratives             # 叙事
python -m soul list-rejections             # 宪法拒绝日志
python -m soul verify-constitution         # 校验所有叙事通过宪法
```

测试用 `SOUL_DATA_DIR=<临时目录>` 隔离，不污染真实 `data/`。

## 核心原则（Phase 5 写死）
```
Memory preserves what happened.  记忆保存事实。
Narrative evolves what it means. 叙事更新意义。
Identity emerges from that evolving meaning.  自我诞生于意义的持续演化。
```
**Narrative 可以改变意义，但不能改变事实。**

## 版本

- 当前版本：`0.4.0`（Phase 1-14：骨架→证据→记忆→慢循环→宪法→信念/关系→自我→目标→优先级/进度→计划→决策→长期目标连续性→动机方向→执行门）
- 规划路线见 `docs/ROADMAP.md`

## Phase 11：Decision Agent（推荐下一步 review，不执行）

```bash
python -m soul run-decision-cycle      # 从 active goal/plan/task 推荐下一 review 步
python -m soul show-current-decision   # 最新 waiting_for_review 决策
python -m soul list-decisions          # 列出 decisions
python -m soul verify-decisions        # 校验 decision 全过 Constitution
```

核心：decision 只推荐"下一步人工 review 哪个 task"，**manual_review_required=true、execution_allowed=false**（不授权执行）；引 goal_id/plan_id/task_id + evidence_ids；无可选时 defer/blocked。不做自动行动也不是执行许可。

## Phase 10：Planning Agent（证据bound 计划，不执行）

```bash
python -m soul run-planning-cycle   # 读 active goals → Priority → 生成 plan+tasks（过 Constitution）
python -m soul show-current-plan    # 最新 active plan 及其 tasks
python -m soul list-plans           # 列出 plans
python -m soul list-tasks           # 列出 tasks
python -m soul verify-plans         # 校验 plan/task 全部过 Constitution
```

核心约束：plan 引 goal_id + evidence_ids + 至少一类 source；task 默认 `execution_mode=manual_only`、`status=proposed`；**全部不自动执行**（不调 API / 不发邮件 / 不改文件）。Planning 只描述"未来可做什么"，真正的 Decision/Motivation 放更后面且继续受 Constitution 拦。

## Phase 12：Goal Continuity（长期目标连续性 / Long-term Goal Consolidation）

```bash
python -m soul run-goal-consolidation-cycle   # 读 active goals → 归并连续性 → 建长期目标+归并记录（过宪法）
python -m soul list-long-term-goals           # 列出长期目标
python -m soul list-goal-consolidations       # 列出归并记录
python -m soul show-goal-continuity           # 查看 active 长期目标及其来源
python -m soul verify-goal-continuity         # 校验长期目标/归并记录全过 Constitution
```

核心：把分散的 local goals 按「连续性方向」（project_phase / safety / verification / maintenance）归并成 long-term goal，让后续 Motivation 不变成乱跳的"欲望生成器"。**MVP 不用 LLM**，规则式分组；须 **≥2 个 source goals**（safety 例外）；evidence 必引；progress/priority 0-1；**不自动 completed、不删/覆盖 source goals**（旧版本用 supersedes）；decision 附加只读的 `related_long_term_goal_ids` + `continuity_context`，不改变选择逻辑。真正 auto execution 仍在更后面且继续受 Constitution 拦。

## Phase 13：Motivation Agent（Evidence-bound Direction / Why Layer）

```bash
python -m soul run-motivation-cycle           # 读 active 长期目标/local goals/信念/叙事/反思 → 生成方向 motivation（过宪法）
python -m soul list-motivations               # 列出 motivations
python -m soul show-active-motivations        # 查看 active motivations 及其来源
python -m soul verify-motivations             # 校验 motivations 全过 Constitution
```

核心：**Motivation 只能解释"为什么继续"，不能决定"现在去做"。** 按 4 条连续性规则（project_continuity / safety_boundary / verification_traceability / maintenance_continuity）把现有状态归拢成"值得持续关注的方向"。MVP 不用 LLM，纯规则；`motivation_score` 由 6 因子加权（long_term_goal_strength / evidence_strength / safety_weight / progress_relevance / decision_relevance / continuity_weight，0-1）；evidence 必引。

**硬边界**（与 Goal / Planning / Decision / Execution）：
- Goal 记录方向 → Planning 拆 plan/task → **Decision 从已有 task 推荐下一步 review** → **Motivation 解释为什么值得继续** → *Execution 本项目当前不做*。
- Motivation 不允许创建 goal/plan/task、执行、改任何状态、绕过人工 review；`manual_review_required=true`、`execution_allowed=false`；direction/reason 禁自主欲望/绝对化词（"我想要/我必须/永远/唯一"等）。
- Decision 可**只读**读取 `related_motivation_ids` 作方向上下文，不改选择逻辑、不新建 task、不改变 execution_allowed=false。真正 Permission / Execution Gate 是更后面阶段的事。

## Phase 14：Permission / Execution Gate + Sandbox Action Adapter

```bash
python -m soul list-action-registry           # 列 action registry（L0/L1/L2/L∞ 白名单）
python -m soul run-execution-gate             # 读最新 decision → Gate 裁决 → Constitution → 落 execution_request
python -m soul list-execution-requests        # 列 execution requests
python -m soul show-execution-request <id>    # 查看单个 execution request
python -m soul approve-execution <id> --reason <r>   # 审批 L1（拟稿级）request
python -m soul reject-execution <id> --reason <r>    # 拒绝 request
python -m soul run-approved-action <id>       # 执行 auto_allowed / approved 的动作
python -m soul list-action-logs               # 列 action logs
python -m soul verify-executions              # 校验 execution 体系完整性（11 项检查）
```

核心：**Execution Gate 是动作从"建议"到"执行"的唯一闸点**。`execution_allowed` 只能由 Permission Gate 裁决，绝不来自 Decision。按审批阶梯 **L0（内部 sandbox 自动）/ L1（拟稿确认）/ L2（真实业务 blocked）/ L∞（永远 reject）** 分配动作等级：

- **L0**：4 个内部 sandbox 动作（`internal_record_review_note` / `internal_create_checklist_snapshot` / `internal_run_readonly_verification` / `internal_append_sandbox_result`），只写 Project Soul 自己的 SQLite + evidence log，可自动执行。
- **L1**：拟稿/审阅类（`generate_internal_draft` / `prepare_review_summary` / `create_internal_plan_note`），Phase 14 需 human approval 后才可执行。
- **L2**：真实业务（钱/客户承诺/发货修正/改订单），Phase 14 一律 blocked 不执行。
- **L∞**：硬禁区（删 evidence / 改 hash chain / 改付款金额 / 绕过宪法等），永远 reject 即使有 approval。

**Sandbox Action Adapter**（`soul/agents/action_adapter.py`）执行批准的动作：返回 `ActionResult` → 写 `action_logs` → 把执行结果**追加为新 evidence**（`event_type=action_result`，hash chain 继续有效）→ 不修改 goal/plan/task/decision 状态。**Phase 14 只做项目内部 sandbox 证明闭环可运行；做完前不接 LEBREW 真实业务手臂（Phase 15）。**
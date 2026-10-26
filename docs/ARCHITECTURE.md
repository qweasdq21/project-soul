# ARCHITECTURE

Project Soul / Soul Factory 是一个**多 Agent 认知工厂**。内部由多个协作 Agent 完成认知循环，对外只暴露一个 `Conversation Agent`（本阶段未实现）。

> 核心立场：人格不是配置，而是状态。Self 是多个子系统长期协作后收敛出的当前一致状态，不是单一 prompt 扮演。

## 总体架构图

```
                        ┌────────────────────────────────────────────┐
                        │            Orchestrator Agent             │
                        │  任务编排 | 双回路调度 | 全局状态位图      │
                        └────────────────────────────────────────────┘
                                ▲ 调度            ▲ 汇报
        ┌───────────────────────┴──────┬──────────┘
        │ Fast Loop(实时)             │ Slow Loop(离线/周期)
        ▼                              ▼
┌──────────────────────┐      ┌──────────────────────┐
│ Perception Agent     │      │ Consolidation        │
│ Emotion Agent        │      │ Pattern Mining       │
│ Importance Agent     │      │ Belief Agent         │
│ Working Memory       │      │ Relationship Agent   │
│ Decision Agent       │ ───▶ │ Narrative Agent      │
│ → Action             │      │ Goal Agent           │
│ → Short Reflection   │      │ Motivation Agent     │
│ → Episode Queue      │      │ Self Model Agent     │
└──────────────────────┘      │ Constitution Check   │
                              │ Versioned Commit     │
                              └──────────────────────┘
                                      │
                              ┌───────▼────────┐
                              │  Constitution   │  ── 所有模块输出的唯一守门员
                              │     Agent       │
                              └───────┬────────┘
                                      │ 仅通过校验的更新才落库
                        ┌─────────────▼─────────────┐
                        │        数据层             │
                        │ evidence(不可变追加)      │
                        │ episodes / memory         │
                        │ beliefs / relationships   │
                        │ narratives / goals        │
                        │ self_snapshots(快照)      │
                        └───────────────────────────┘
```

**关键设计**：Constitution Agent 不是众多模块之一，而是**唯一的写入守门员**。Fast Loop 只产生**候选更新**，真正落盘交给 Slow Loop + Constitution。

## 双回路

### Fast Loop / Realtime Cognitive Loop
```
World/User/Tool Result
   → Perception(结构化 event)
   → Emotion Appraisal(工程情绪向量，8 维)
   → Importance 评估(是否进 working/episode memory)
   → Working Memory
   → Decision(下一步 action)
   → Action(执行，产生 outcome)
   → Short Reflection(轻量，只写"候选")
   → 追加到 Episode Queue(异步，不阻塞)
```
约束：快速、低延迟、不做重型 pattern mining、不直接改写 long-term self、只产生候选更新。

### Slow Loop / Offline Self Update Loop
```
Episode Queue
   → Consolidation(合并事件成 episode)
   → Pattern Mining(统计模式)
   → Belief Update(候选)
   → Relationship Update(候选，带原因)
   → Narrative Update(候选，引用 evidence)
   → Goal Update / Motivation
   → Self Model Update(汇总)
   → Constitution Check(逐条校验)
   → Versioned Commit(仅通过校验的写库)
```
约束：慢速、可解释、可回滚、有版本记录、不修改 Reality Layer、所有 self 更新必须有 evidence references。

## Agent Society（15 个，本阶段 9 个实现为占位，6 个预留 stub）

| Agent | 职责 | 实现状态 |
|---|---|---|
| Orchestrator | 协调所有子 Agent，控制任务流，维护全局循环 | MVP |
| Perception | 把消息/事件转成结构化 Experience Event | MVP |
| Emotion/Appraisal | 生成 8 维工程情绪向量 appraisal | MVP |
| Importance | 多因子评估事件重要性，决定进哪层 memory | MVP |
| Memory | 管理 6 层记忆（Working/Episode/Semantic/Relationship/Core/Archive） | MVP |
| Reflection | Short（行动后）+ Long（周期）反思 | MVP |
| Narrative | 把 episode 组织成 meaning/story（仅解释，不改证据） | MVP |
| Constitution | 校验 4 条宪法，所有写库的守门员 | MVP |
| Self Model | 汇总各模块 = emergent self snapshot | MVP |
| Belief | 从 evidence/pattern/reflection 形成或修正信念 | 预留 stub |
| Relationship | 维护对象的关系模型（trust/familiarity/...） | 预留 stub |
| Motivation | 从 needs/gaps/relationships/goals/values 生成 motivation | 预留 stub |
| Goal | 维护 goal 生命周期 | 预留 stub |
| Planning | 把 goal 拆成 plan/tasks | 预留 stub |
| Decision | 综合 self/memory/goals/beliefs/relationships/emotion 决定下一步 | 预留 stub |

## 数据流原则

- 只允许 **append** written to Reality Layer（evidence）。
- Belief / Relationship / Narrative / Self 更新必须有 evidence 引用。
- 每次 self 更新受 Constitution 03（身份稳定）的幅度限制。

> 本文件描述目标架构；当前 Phase 1 仅此图的**骨架占位**。

## Phase 10：Planning Agent v0（Evidence-bound Plan / Task Decomposition）

系统链路在此延伸为：
```
Evidence → Memory → Narrative → Belief / Relationship → Self → Goal → Progress → Plan / Task
```

### Planning Agent 定位
- **只管"未来可做什么"，不是行动系统。**
- 每个 active goal 拆成 1 个 plan + 一组 tasks，全部 evidence-bound（引用 goal_id + evidence_ids + 至少一类 source）。
- **不自动执行、不调用外部工具、不改文件/发邮件/调 API。** task execution_mode 默认 `manual_only`。
- Plan/Task 都必须通过 Constitution 校验才落库；rejected 写入 `constitution_rejections`。
- 真正 Decision / Motivation 放更后面，且继续受 Constitution 拦。

### Plan 不是 action
plan 是 proposed/active 的计划描述，绝不自动 completed。旧 plan 不删除，新版本用 `supersedes` 指针。

### Task 不是 execution
task 是 proposed work item（status 默认 proposed），只能描述"未来可做什么"，不能写成执行命令。`depends_on_task_ids` 只表达顺序依赖，不自动推进。

## Phase 11：Decision Agent v0（Evidence-bound Choice / Next Task Recommendation）

系统链路延伸为：
```
目标 → 进度 → 计划 → 推荐下一步
```

### Decision Agent 定位
- **只推荐"下一步人工 review 的 task"，不给执行许可。**
- 从现有 goals / plans / tasks 里选一个最适合作为下一步的 task，说明为什么选它。
- **manual_review_required=True（必须人工复核）、execution_allowed=False（不授权执行）。**
- 不新建 plan / 不新建 goal / 不改变 task/plan/goal status / 不模拟欲望 / 不调用任何工具。
- 没有可选 task 时产出 defer / blocked（说明原因），不虚构下一步。

### Decision 不是 Action / 不是 Execution Permission
Decision 只输出"建议 review 哪件事"，绝不自动执行、不调用工具、不改文件/发消息/改变外部世界。真正 Motivation / Auto Execution 是后面阶段的事。

## Phase 12：Goal Continuity（Long-term Goal Consolidation）

系统链路延伸为：
```
local goals → (连续性规则分组) → long-term goal + consolidation record → 关联到 Decision（只读）
```

### GoalConsolidationAgent v0 定位
- **只做"归并成长期方向"，不是行动系统、不是欲望生成器。** 让后续 Motivation 知道每个"下一步"属于哪个更大长期方向，避免乱跳。
- 读所有 **active goals**，按 4 条连续性规则（project_phase / safety / verification / maintenance）关键词分组；**≥2 个 source goals**（safety 例外）才归并，否则保守不触发。
- **MVP 不用 LLM，纯规则**：每组建一个 long-term goal（`lgoal-*`）+ 一条 consolidation 记录（`gold-*`），evidence 聚合自 source goals 及其 progress。
- progress = source goals 最新 progress 加权平均（completed 权重折半、单次 delta 上限 0.5、裁剪到 0-1）；priority 取该聚合值（缺省 0.3）。
- **不自动 completed / 不删除 / 不覆盖任何 source goal**（action_taken 禁 delete，旧版本用 supersedes 指针）。
- 通过 Constitution 校验（check_long_term_goal_candidate / check_goal_consolidation_candidate C01-C04）才落库；reject 只写 `constitution_rejections`。

### Long-term goal 不是"我决定要做"
长期目标是"这堆小目标共同指向的连续性方向"的**只读聚合视图**。Decision 可读 `related_long_term_goal_ids` + `continuity_context` 作为上下文，但**不改选择逻辑、不给执行许可**。真正 Motivation / Auto Execution 仍在后面，继续受 Constitution 拦。

## Phase 13：Motivation Agent v0（Evidence-bound Direction / Why Layer）

系统链路至此：
```
local goals + long-term goals + beliefs/narratives/reflections
   → (4 条连续性规则分组) → motivation candidate
   → Constitution check_motivation_candidate(C01-C04)
   → pass → motivations 表；reject → constitution_rejections
   → Decision 只读读取 related_motivation_ids 作方向上下文
```

### Motivation Agent 定位
- **只解释"为什么某个方向值得继续关注"，不决定"现在去做"。** Motiyation 是 Why Layer，不是 Action Layer。
- 输入：active long-term goals + local goals + latest goal progress + accepted narratives + beliefs + semantic memories + reflections + decisions。
- 生成：按 4 条连续性规则（project_continuity / safety_boundary / verification_traceability / maintenance_continuity）把命中同方向的状态归拢成一条 direction + reason。
- `motivation_score` = 6 因子加权（long_term_goal_strength / evidence_strength / safety_weight / progress_relevance / decision_relevance / continuity_weight），0-1，全部可解释。
- **MVP 纯规则，不接 LLM**。evidence 必引、至少一类 source；manual_review_required=true、execution_allowed=false；不创建 goal/plan/task、不改任何状态、不执行外部动作。

### 边界（写死进注释/文档）
- **Goal** 记录要维护或推进的方向；**Planning** 拆 plan/task；**Decision** 从已有 task 推荐下一步 review；**Motivation** 解释为什么值得继续；**Execution** 本项目当前不做。
- Motivation 不允许：创建 goal / 创建 plan / 创建 task / 执行 decision / 执行 task / 修改状态 / 绕过人工 review。
- Motivation 只能作为 Decision 的**只读**参考上下文（related_motivation_ids），不改选择逻辑、不新建 task、不改变 execution_allowed=false。
- 真正 Permission / Execution Gate 是更后面阶段的事（Phase 14+ 见 ROADMAP）。

## Phase 14：Permission / Execution Gate + Sandbox Action Adapter

```
Decision (waiting_for_review)
   │
   ▼
ExecutionGate.evaluate(candidate, action_name, payload)
   │  1. 查 action_registry（未注册/disabled/banned/L∞ → reject）
   │  2. 校验 decision/goal/plan/task/evidence 引用真实
   │  3. 检查 daily_limit 限频 + 外部动作检测（降级 L2 blocked）
   │  4. L0 → auto_allowed；L1 → approval_required；L2 → blocked；L∞ → rejected
   ▼
Constitution.check_execution_candidate(cand)   ← C01-C04 再闸一道
   ▼
SQLiteStore.execution_requests（仅 auto_allowed / waiting_for_approval 落库）
   │
   ├─ L0 auto_allowed ───────────────► run-approved-action（立即，无需审批）
   │
   └─ L1 waiting_for_approval ──► approve-execution/reject-execution（human）
                                        │
                                        ▼
                               run-approved-action（仅 approved / auto_allowed 可执行）
                                        │
                                        ▼
                          ActionAdapter.run(er, payload)
                             ├─ 写 action_logs（executed/failed 都写，不删）
                             ├─ 追加 action_result evidence（hash chain 继续有效）
                             └─ 不改 goal/plan/task/decision status
```

架构要点：
- **execution_allowed 只能由 Permission Gate 裁决**，绝不来自 Decision（Decision 永远 execution_allowed=false）。
- **审批阶梯**：L0 内部 sandbox 自动；L1 拟稿确认（human approval 后执行）；L2 真实业务（钱/承诺/发货/订单）Phase 14 一律 blocked；L∞ 硬禁区永远 reject 即使有 approval。
- ActionAdapter Phase 14 只实现 4 个 sandbox 动作（记 review note / checklist snapshot / 只读验证 / sandbox 闭环证明），全部写自身 SQLite + evidence、不碰外部。
- **verify-executions** 提供 11 项完整性审计（引用真实/L0 仅内部/L1 未批不执行/L2·∞无executed log/evidence 回读一致/无外部动作词/无绕过 Constitution）。
- **边界**：Phase 14 只做项目内部 sandbox 闭环自证；接 LEBREW 真实手臂（邮件拟稿确认、打单录单全自动）是 Phase 15 的事，Gate 安全模型自证前不接真实业务。
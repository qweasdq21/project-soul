# ROADMAP

分阶段推进，先做小闭环再扩展。每阶段结束必须说明：完成了什么、产生了哪些文件、如何运行、如何测试、下一步。

## 阶段一览

| 阶段 | 内容 | 状态 |
|---|---|---|
| **Phase 1 — 骨架** | 目录结构、constitution、schemas、agents/storage/loops 占位、最小 CLI | ✅ 完成 |
| **Phase 2 — 证据链** | Perception → Event → evidence log（JSONL+hash）；Emotion + Importance | ✅ 完成 |
| **Phase 3 — 记忆+反思** | Memory Agent（working/episode）、Reflection Agent | ✅ 完成 |
| **Phase 4 — 慢循环** | episode 聚合 → semantic memory → long reflection | ✅ 完成 |
| **Phase 5 — 宪法+叙事** | Narrative Engine + Constitution Agent（C01-C04 写入门禁） | ✅ 完成 |
| **Phase 6 — 信念+关系** | Belief Agent（evidence-backed）+ Relationship Agent（协作历史） | ✅ 完成 |
| **Phase 7 — 自我快照** | Self Snapshot 聚合 belief/narrative/relationship + versioning + similarity | ✅ 完成 |
| **Phase 8 — 目标** | Goal Agent 从证据长出目标 + 生命周期 + active_goals 接入 Self | ✅ 完成 |
| **Phase 9 — 目标优先级+进度** | Goal Priority Ranking（computed_priority 6 因子）+ Goal Progress Tracking | ✅ 完成 |
| **Phase 10 — 计划** | Planning Agent v0：active goal → plan + tasks，evidence-bound，不执行 | ✅ 完成 |
| **Phase 11 — 决策** | Decision Agent v0：推荐下一步 review 的 task，只给建议不给执行许可 | ✅ 完成 |
| **Phase 12 — 长期目标连续性** | Goal Continuity / Long-term Goal Consolidation：active goals 归并为长期方向，规则式 | ✅ 完成 |
| **Phase 13 — 动机方向** | Motivation Agent：Evidence-bound Direction / Why Layer，解释为什么继续，不决定去做 | ✅ 完成 |
| **Phase 14 — 执行门** | Permission / Execution Gate + Action Adapter：先内循环证明能审批/拒绝/限权/记录/回写 evidence/审计 | ✅ 完成 |
| **Phase 15 — 动机/执行** | Motivation 已建；Execution Gate 后接 LEBREW 真实上肢（邮件拟稿确认/打单录单全自动） | ⏳ 规划 |

## Phase 13 明确不做

- 接入 LLM / 模型推理（MVP 纯规则，可解释）
- 创建 goal / plan / task（Motivation 只解释与记录方向，不生成行动结构）
- 修改任何 goal / plan / task / decision 状态
- 执行 decision / task / 调用工具 / 改文件 / 发消息
- 把 motivation 当"我决定现在去做"
- Permission / Execution Gate / auto-execution（那是 Phase 14+）

## Phase 12 明确不做

- 自动归并出 LLM / 接入模型推理（MVP 纯规则，可解释）
- 自动 completed / 删除 / 覆盖任何 source goal（只建 parent，不改子）
- 把长期目标当"我决定下一步要做什么"（Decision 仍只给 review 建议）
- Motivation / Auto Execution / 调用工具 / 改文件 / 发消息（那是 Phase 13+）

## Phase 11 明确不做

- Motivation / Auto Execution（那是 Phase 12+）
- 自动执行 task / 调用工具 / 改文件 / 发消息
- 改变 task/plan/goal status
- 把 decision 当"我决定执行"

- Decision / Motivation / Auto Execution（那是 Phase 11+）
- 接入 LLM / 调用 API
- plan/task 自动执行或写外部系统
- 把 planning 当"我决定行动"

## 第一版红线（任何阶段）

- 不修改 evidence（Reality Layer 只追加）
- 不造假记忆
- 不以叙事覆盖事实
- 不操控用户
- 不声称 AI 有真实意识
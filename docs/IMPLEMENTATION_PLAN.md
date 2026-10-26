# IMPLEMENTATION_PLAN

Project Soul / Soul Factory 完整实施计划（v0.1）。

## 1. 项目名称与目标
多 Agent 认知工厂，研究 AI Agent 如何通过经历/记忆/信念/关系/叙事/目标/反思逐步形成稳定自我模型。

## 2. 定位
并非证明 AI 有意识，而是实现**可解释、可回滚、可审计的自我状态演化系统**。

## 3. 总体架构
见 `docs/ARCHITECTURE.md`：Orchestrator + Fast/Slow 双回路 + 15 Agent Society + Constitution 守门 + 分层数据。

## 4. Fast / Slow Loop
见 ARCHITECTURE.md 双回路节。

## 5. Agent 职责
见 ARCHITECTURE.md Agent Society 表。

## 6. 数据层
见 `docs/DATA_MODEL.md`：8 类结构 + JSONL/SQLite/Markdown 存储。

## 7/8. Evidence 与 Narrative 边界 / Narrative Engine
见 DATA_MODEL.md 与 SAFETY_AND_CONSTITUTION.md；SAFETY 含 Constitution 防篡改机制。

## 9. Constitution Agent
唯一写入守门员，执行 4 项 check（C01 证据不可变 / C02 可解释 / C03 身份稳定 / C04 不操控），整批事务提交。

## 10. Memory/Belief/Relationship/Goal/Self 协作
数据流：Perception→Evidence；Slow Loop 由 evidence+pattern→belief/relationship；belief/relationship→goal 排序与 motivation；全部聚合→self snapshot（emergent consensus，非单模块设定）。

## 11. MVP 范围
接收 1 条 event → Perception→Event→不可变 evidence log→Emotion appraisal→Importance→(working+episode memory)→Short reflection→Narrative(引用证据)→Constitution 校验→Self snapshot→输出完整 trace。不跑长期自动运行。

## 12. 第一版不做
长期自动运行、UI、多用户、云部署、向量库、自动工具操作、情感拟人化、大规模检索、真实历史导入（接口先预留）。

## 13. 分阶段路线
见 `docs/ROADMAP.md`（Phase 1 骨架 → Phase 7 增强）。

## 14. 测试方案
单元（含 Constitution 4 项）/ 不变性（hash 链）/ 回滚 / 稳定性 / 可解释 / 对抗．

## 15. 风险与红线
概念膨胀 → 精简 Agent；自证陷阱 → 强制宪法+全 trace；存储膨胀 → archive+decay；过度拟人 → C04 检测器。红线：不篡改证据、不造假记忆、不覆盖事实、不操控用户、不声称意识。

## 16. 确认事项
见 README 与各 doc；关键决策（Agent 精简度、情绪 8 维、事务回滚粒度、测试事件源、Self 相似度规则、独立存储目录）均已由用户确认。
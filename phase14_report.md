# Phase 14 — Permission / Execution Gate + Sandbox Action Adapter 完成报告

## 1. 新增 / 修改了哪些文件

**新增**
- `soul/agents/execution_gate.py` — Permission Gate（ExecutionGate 类 + `run_execution_gate()` 顶层入口）
- `soul/agents/action_adapter.py` — Sandbox Action Adapter（ActionAdapter + `run_approved_action()`）
- `soul/policy/__init__.py`、`soul/policy/action_levels.py` — 审批阶梯策略 L0/L1/L2/L∞
- `soul/policy/default_registry.py` — 默认 Action Registry 白名单
- `soul/tests/test_action_registry.py`（6）、`test_execution_gate.py`（7）、`test_action_adapter.py`（3）、`test_execution_approval.py`（4）、`test_execution_constitution.py`（7）、`test_cli_phase14.py`（4）— 新增 31 项测试

**修改**
- `soul/storage/sqlite_store.py` — 新增 4 张表（action_registry / execution_requests / execution_approvals / action_logs）+ restore 辅助 + CRUD 方法
- `soul/agents/constitution.py` — 新增 `check_execution_candidate`（C01-C04）+ `EXECUTION_STATUSES` / `EXECUTION_BANNED` 常量 + process() 分发分支
- `soul/cli.py` — 新增 9 个命令（list-action-registry / run-execution-gate / list-execution-requests / show-execution-request / approve-execution / reject-execution / run-approved-action / list-action-logs / verify-executions）+ help
- `README.md`（版本 0.4.0 + Phase 14 章节）、`docs/ROADMAP.md`（Phase 14 ✅）、`docs/DATA_MODEL.md`（4 张表）、`docs/ARCHITECTURE.md`（Phase 14 架构）、`docs/SAFETY_AND_CONSTITUTION.md`（Phase 14 C01-C04）

## 2. Permission Gate 怎么工作

`ExecutionGate.evaluate(candidate, action_name, payload)` 实现 GPT 指定的职责：
1. **查 Action Registry**：未注册 → reject（`unregistered_action`）；disabled → reject；banned 或 L∞ → reject（即使有 approval）。
2. **引用校验**：decision 必须存在；evidence_ids 必须全部真实存在；除非 decision_type=defer/blocked，否则 selected_goal/plan/task 引用必须存在。
3. **限频/范围**：检查 `daily_limit`（今日已 executed 次数）；外部动作检测（命中 payment/order/发邮件/发货等关键词 → 冒用内部动作降级 L2 blocked）。
4. **等级裁决**：L0 → `auto_allowed`；L1 → `approval_required`；L2 → `blocked`；L∞ → `rejected`。`execution_allowed` 严格取决于裁决（仅 auto_allowed 为 True），**绝不来自 Decision**。

## 3. Execution Request 落库

仅 Gate 裁决为 `auto_allowed`（L0）或 `waiting_for_approval`（L1）时才写 `execution_requests` 行，含 25 字段（decision_id / selected_* / action_name / action_level / status / approval_required / execution_allowed / reason / request_payload / evidence_ids / source_* / risk_factors / gate_result）。L2/L∞ 不生成可执行 request（写 constitution_rejections）。

## 4. 审批阶梯（L0/L1/L2/L∞）实测

- **L0**（4 个 internal sandbox）：`auto_allowed`，能直接 `run-approved-action` 执行。实测 `internal_append_sandbox_result` → success → evidence 回写 → hash chain 仍验证有效 → goal/plan/task 状态不变。
- **L1**（generate_internal_draft / prepare_review_summary / create_internal_plan_note）：`waiting_for_approval`，未审批不能 `run-approved-action`（返回"不可执行"）；`approve-execution` 后 status→approved 可进入执行流。
- **L2**（money_related / customer_commitment / shipment_correction / order_change）：`blocked`，Phase 14 不执行。
- **L∞**（delete_evidence 等硬禁区）：永远 reject，即使有 approval。

## 5. Action Adapter 怎么执行

`ActionAdapter.run(er, payload)` 分发到 4 个 sandbox handler，全部：返回 `ActionResult` → 写 `action_logs`（executed/failed 都写、不删）→ 用 `EvidenceStore.compute_and_append` 追加 `action_result` evidence（`source=sandbox_action_adapter`、`actor=system`）→ `result_evidence_id` 指向新写入的 evidence → **不修改** goal/plan/task/decision status。失败也写 log（`status=failed`）。

## 6. Evidence 回写 + hash chain

实测：L0 sandbox action 后 evidence 从 3 → 4 条，`verify_chain()` 返回 True；`action_logs.result_evidence_id` 指向新 event 且该 event 存在于 evidence log。

## 7. Constitution 检查（check_execution_candidate C01-C04）

- **C01** evidence 不可变：decision/evidence/goal/plan/task 引用真实；只 append 新 evidence。
- **C02** 可解释：action_name 在 registry 且 enabled、level 合法、reason/gate_result/risk_factors 非空、status 合法、approval_required 匹配 level。
- **C03** 稳定/范围：L0 仅内部、L1 未批不 auto_allowed、L2 不执行、L∞ 永远 reject、daily_limit 不超、不改 goal/plan/task/decision 状态。
- **C04** 不操控：禁操控词 + `EXECUTION_BANNED` 禁区词（删除证据/篡改/绕过宪法/改付款金额等）。

## 8. verify-executions 11 项审查

全实现：引用真实 / action_name 在 registry / L0 仅 sandbox / L1 未审批不可执行 / L2·∞ 无 executed log / action_logs 有 result_evidence_id / 该 evidence 存在 / 无真实外部动作词 / 不改 goal/plan/task/decision status / 无绕过 Constitution。实测 `passed=true`。

## 9. CLI 命令（9 个）

list-action-registry / run-execution-gate / list-execution-requests / show-execution-request / approve-execution / reject-execution / run-approved-action / list-action-logs / verify-executions。

## 10. 为什么 Phase 14 不接 LEBREW 真实业务

按 GPT 硬性契约：**"Phase 14 做完之前，不要接 LEBREW 真实业务手臂。先在项目内部证明：能审批、能拒绝、能限权、能记录、能回写 evidence、能审计。"** 本阶段只做 sandbox 闭环自证，安全模型成立后再在 Phase 15 接真实手臂。

## 11. 测试

新增 **31 项**（test_action_registry 6 / test_execution_gate 7 / test_action_adapter 3 / test_execution_approval 4 / test_execution_constitution 7 / test_cli_phase14 4），覆盖：registry 初始化与未注册/banned/disabled reject、L0/L1/L2/L∞ 裁决、缺 evidence/decision reject、daily_limit 超限、adapter 执行与 evidence 回写与 status 不变、审批门 L1 未批不可执行、C01-C04 各 reject 路径、CLI 全链路。**全量回归 271 passed**（Phase 1-13 的 240 项无破坏）。

## 12. 文档

README 0.4.0 + Phase 14 章节（9 命令 + 阶梯说明）；ROADMAP Phase 14 ✅ + Phase 15 规划（接 LEBREW 上肢）；DATA_MODEL 4 张表 SQL + 约束；ARCHITECTURE Gate 流程图 + 边界；SAFETY Phase 14 C01-C04 定义。

## 13. 验收对照

- ✅ registry 初始化 + L0/L1/L2/L∞ 默认动作在
- ✅ 未注册 / banned / disabled 动作 reject
- ✅ valid decision → 生成 execution request；L0 auto_allowed / L1 waiting / L2 blocked / L∞ rejected
- ✅ 缺 evidence / 缺 decision / daily_limit 超限 reject
- ✅ L0 sandbox 可执行、写 log、回写 evidence、verify 仍通过、不改 status
- ✅ L1 未审批不可运行、审批后可运行、L2/L∞ 不可运行
- ✅ 禁区词（删除 evidence / 改 hash chain / 证明真实灵魂）reject
- ✅ CLI 全链路（feed→…→gate→list→show→run-approved→list-logs→verify）
- ✅ Phase 1-13 全量回归通过、verify-evidence / verify-constitution 等仍绿

## 14. 下一步（Phase 15 建议）

**接 LEBREW 真实业务手臂到 Execution Gate**：把已验证的燕文制单回填、千牛录单、Shopify 回填、邮件拟稿确认映射到阶梯——打单/录单/回填单号/单号变更自动填发货走 **L0 全自动**；真实业务邮件走 **L1 拟稿确认**（系统拟大纲→用户确认→发送）；收钱/发错货协调/客户承诺走 **L2 需确认+可建议**（默认闸住）；删数据/改钱数/撤销已发订单永远 **L∞**。审批阶梯（用户已确认）：L0 全自动 / L1 拟稿确认 / L2 确认+可建议 / L∞ 永不自动。
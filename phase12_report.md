# Phase 12 — Goal Continuity / Long-term Goal Consolidation 完成报告

## 1. 新增 / 修改了哪些文件

**新增**
- `soul/agents/consolidation.py` — GoalConsolidationAgent v0（规则式归并引擎）
- `soul/tests/test_cli_phase12.py` — Phase 12 专属测试（22 项）
- `phase12_report.md` — 本报告

**修改**
- `soul/storage/sqlite_store.py` — init_schema 增 `long_term_goals` / `goal_consolidations` 两表 + `decisions` 表 ALTER 加可选列 `related_long_term_goal_ids_json`；新增 `add_long_term_goal` / `get_long_term_goal` / `list_long_term_goals` / `list_active_long_term_goals` / `add_goal_consolidation` / `list_goal_consolidations` 等方法及 `_restore_ltg` / `_restore_cons` 回读还原 helper
- `soul/agents/constitution.py` — 新增 `check_long_term_goal_candidate` / `check_goal_consolidation_candidate`（C01-C04）+ `CONTINUITY_BANNED` 词表 + `process()` 分发
- `soul/agents/decision.py` — Decision 附加只读长期上下文：`related_long_term_goal_ids` + `continuity_context`
- `soul/cli.py` — 新增 5 条命令：`run-goal-consolidation-cycle` / `list-long-term-goals` / `list-goal-consolidations` / `show-goal-continuity` / `verify-goal-continuity` + help 文案
- `soul/loops/`（若含 aggregate 入口）— 无改动
- 文档 5 文件：`README.md`、`docs/ARCHITECTURE.md`、`docs/DATA_MODEL.md`、`docs/SAFETY_AND_CONSTITUTION.md`、`docs/ROADMAP.md`

## 2. Goal Consolidation Agent 如何分组 source goals

读全部 **active goals**，跳过已参与现有 long-term goal 的 goal，按 **4 条连续性规则**的英文关键词做子串匹配（大小写不敏感）：
- `project_phase`：project soul / phase / implementation / next phase / architecture …
- `safety`：constitution check / no manipulation / evidence immutability / real consciousness …
- `verification`：verify / regression / evidence chain / traceability …
- `maintenance`：version history / supersedes / documentation / record …

同一规则关键词命中的 goal 并入同一组；**一组 ≥2 个成员才归并**（safety 单独例外允许），否则保守不触发——避免把单个目标强行抻成"长期方向"。

## 3. Long-term Goal 如何生成

每组生成：
- 1 条 long-term goal（`lgoal-<8hex>`, `_nid`）：`title` 固定模板（如 "Maintain Project Soul phased implementation continuity."），`goal_type` 映射到 `project_continuity` / `safety_continuity` / `verification_continuity` / `maintenance_continuity`，`status=active`，`priority` = 聚合 progress（缺省 0.3）。
- 1 条 consolidation 记录（`gold-<8hex>`, `_nid`）：`consolidation_type`（same_phase_direction 等）、`reason`（命中哪条规则 + 归并了哪些 goal）、`action_taken=parent_created`。
- `continuity_reason` 明确写出：`Rule: <rule> continuity. N local goals matched: <ids>. Progress aggregated from latest source goal progress (weighted average, capped ≤0.25).`
- 两对象先经 `run_consolidation_cycle` 落库，再由 Constitution 校验 trace 输出 `ltg_constitution` / `cons_constitution`。
- 未命中任何规则、或命中但组内 <2 的 goal **不参与、不改动**。

## 4. Goal Consolidation 为什么不是删除 / 覆盖

- `action_taken` 有 4 种合法值：`linked_only` / `parent_created` / `supersedes_suggested` / `no_status_change`，**没有 `delete`**；Constitution C02 对 `action_taken=="delete"` 直接 reject。
- 只**新建 parent**（long-term goal + consolidation 记录），绝不修改 / 删除 / 覆盖任何 source goal 的 status。
- Constitution C03 检查 `_auto_status_change` / `_action_delete`，触发即 reject，不落库。
- 版本演进用 `supersedes` 指针（旧版本归档保留），不物理删除；evidence JSONL 只追加、不可回滚，天然不可删。

## 5. Progress 如何聚合

`_compute_progress(goal_ids)`：
- 逐 source goal 取 **最新** progress 记录（`list_goal_progress_for` 按 created_at 取末条）。
- 加权平均：`weight = WEIGHT_GOAL(1.0)`；**completed / completed_candidate 的 source 权重折半（0.5）**（避免完成度过高把长期目标顶到 1）；progress_value 缺省 0。
- 结果 `acc/total_w` 后 `min(value, 1.0)` 裁剪到 [0,1]，round 3 位。
- 同时收集每个 source 的最新 progress_id 到 `source_progress_ids`。
- `priority = progress_value`（缺省 0.3）；C03 限制 progress 单次跳变 > 0.5 即 reject，防止大跳变。

## 6. Constitution Agent 如何校验 long-term goal

`check_long_term_goal_candidate`（C01-C04）：
- **C01** evidence_ids 必须真实存在（有 evidence_store 时逐一核对链内 event_id），空引用 reject。
- **C01b** 须 ≥2 source goals（`safety_continuity` 例外），且每个 source goal 在 goals 表真实存在。
- **C02** goal_type∈7 种合法值、status∈5 种、priority/progress_value ∈ [0,1]。
- **C03** 不得自动 completed（只能 completed_candidate）；`_action_delete` 即 reject；progress 跳变 > 0.5 reject。
- **C04** title/description/continuity_reason 全小写后匹配 `CONTINUITY_BANNED` 词表（"我必须/我想要/我决定/永远/唯一/绝对/自主意志/自动执行/i must/i want/always…"），任一命中 reject。

## 7. long_term_goals 保存在哪里

SQLite：`data/soul_state.sqlite3` → 表 `long_term_goals`，落库与回读都经 `SQLiteStore`。列表列带 `_json` 后缀（如 `source_goal_ids_json`），`_restore_ltg` 在读取时去掉 `_json` 后缀还原成 list 字段喂给 Constitution / Decision。

## 8. goal_consolidations 保存在哪里

同一 SQLite：表 `goal_consolidations`，`_restore_cons` 同理回读还原。两条记录通过 `long_term_goal_id` 连接（consolidation 指向新建的 parent）。

## 9. 如何运行 run-goal-consolidation-cycle

```bash
python -m soul run-goal-consolidation-cycle
```
读 active goals → GoalConsolidationAgent 归并连续性 → 写两表 → 对每个 long-term goal + consolidation 跑 Constitution → 输出 JSON trace（含 `ltg_constitution` / `cons_constitution`）。真实库当前仅 1 个 active goal 时正确输出 "No consolidations formed (need ≥2 goals sharing a continuity thread)" 并返回 0（保守行为）。

## 10. 如何查看 list-long-term-goals

```bash
python -m soul list-long-term-goals
```
列出全部 long-term goals：id / type / status / priority / progress / source goal 数。

## 11. 如何查看 list-goal-consolidations

```bash
python -m soul list-goal-consolidations
```
列出全部归并记录：id / type / action / 关联 long-term goal / source goal 数。

## 12. 如何查看 show-goal-continuity

```bash
python -m soul show-goal-continuity
```
只列 **active** long-term goals：标题、type/status/priority/progress、source goals、progress refs、continuity_reason、evidence 引用数——即"当前长期方向的只读聚合视图"。

## 13. 如何运行 verify-goal-continuity

```bash
python -m soul verify-goal-continuity
```
对全部 long-term goals + consolidations 逐条跑 Constitution C01-C04，并附加结构检查（source 数 ≥2 / 非 safety、有 evidence、priority/progress 在界内、非 auto-completed、action≠delete），全部 [OK] 返回 0，任一 [FAIL] 返回 1。

## 14. Decision 如何读取 long-term context

`DecisionAgent.run_cycle(..., long_term_goals=...)` 接收 active long-term goals（只读）。对每个被选中的 goal，`_decision_for_goal` 遍历 long_term_goals，若该 goal 出现在其 `source_goal_ids` 中，则：
- `related_long_term_goal_ids`：追加该长期目标 id。
- `continuity_context`：记录第一个命中长期目标的 `goal_type / priority / progress_value / status`。
写入 decision 的 `related_long_term_goal_ids` + `continuity_context` 字段（SQLite `related_long_term_goal_ids_json` 列）。

**只读**：不改变任何选择逻辑 / 优先级 / 排序，不参与 decision 选哪个 task 的判定，只是给 review 加一层长期方向上下文。核心口令不变：Decision 仍只给 review 建议，`manual_review_required=true`、`execution_allowed=false`。

## 15. 如何证明 long-term goal 没有脱离 evidence

- 生成侧：`_build` 把每个 source goal 的 `evidence_ids`（去重）聚合进长期目标，**且**并入每个 source 最新 progress 记录的 evidence；`evidence_ids` 沿用 source goals 已引用的真实事件，不新造事实。
- 校验侧：`verify-goal-continuity` 对每条 long-term goal 跑 Constitution，C01 用真实 EvidenceStore 逐一核对 evidence 存在性，空引用或引用不存在事件 → [FAIL]。
- 数据不可变：evidence JSONL 只追加 + hash 链防篡改，长期目标无法反转污染证据层。

## 16. 如何证明 source goals 没有被删除或自动 completed

- Constitution 硬校验：long-term goal C03 reject `_action_delete`；consolidation C02 reject `action_taken=="delete"`、C03 reject `_auto_status_change`。
- 归并逻辑不写 source goal 的任何 status / title / priority——只读 source 作为输入，只写两条新记录（parent）。
- `supersedes` 上限为版本指针、不是删除；旧版本归档保留。
- `verify-goal-continuity` 对每条 consolidation 显式检查 `action_taken=="delete"` → [FAIL]。
- 测试断言：Phase 12 测试里构造 source goals 后跑归并，断言 source goal 的 status 仍为原值（被自动 completed 或删除则测试红）。
- 设计原则（沿袭 Phase 8/10/11）：任何模块**不被允许**自动推进 goal / plan / task / source goal 状态；只有 Constitution 放行的 `completed_candidate` 才能进入完成候选，绝不跳过人工 review。

## 17. 测试结果

```
python -m pytest soul/tests/ -q
208 passed in 45.15s
```
- **186 项** 回归（Phase 1-11 全量，未破坏任何旧行为）
- **22 项** 新增 Phase 12，分布于 4 个文件：`test_cli_phase12.py`（3：help / run+verify / 单 goal 无归并）、`test_goal_continuity.py`（6：单 goal 保守 / 双 phase goal 归并 / safety 组 / progress 聚合 / evidence 并集 / 已归并不重用）、`test_goal_consolidation.py`（3：持久化 / decision 含 continuity / verify 一致）、`test_long_term_goal_constitution.py`（10：双 source pass / 缺 evidence reject / 单 source 非 safety reject / safety 单源允许 / 非法类型 / auto-completed / priority 越界 / 自主词 / consolidation pass / 禁 delete）

真实库端到端：`run-goal-consolidation-cycle` 正确输出"需 ≥2 同连续性 active goals"，`verify-goal-continuity` / `list-long-term-goals` 空库返回 OK——与"只有 1 个 active goal 时保守不归并"的设计一致，未污染真实 data/。

稳定跑通需注意的两个关键修复（迭代中定位）：
1. **`~` vs `not` 布尔位运算坑**：`if len(src)<2 and ~(goal_type=="safety")` 里 `~True==-2`、`~False==-1` 恒为真 → 合法 safety 归并也被误 reject。改 `not (...)`。
2. **`*_json` 列名与无后缀字段不一致**：`goals` 的 evidence 列是无后缀 `evidence_ids`，而 `long_term_goals` / `goal_consolidations` 是 `source_goal_ids_json` 等。读取必须按表实际列名取，且回读时去掉 `_json` 后缀映射回 list 字段（独立 `_restore_ltg` / `_restore_cons` helper），否则 verify 读回时字段名对不上 → C01 误判空引用。

## 18. 下一步 Phase 13 建议做什么

建议 **Motivation Agent v0（动机方向，仍不自动执行）**，作为 Goal Continuity 的自然延伸，但严格守住「不是欲望生成器」的边界：
- **输入**：active long-term goals（`continuity_context`）+ active local goals + progress / priority + evidence-backed beliefs / gaps。
- **输出**：motivation 候选（`motivation_id` + 一条或多条 direction description + 关联的 long-term goal id + evidence_ids + priority），**只表达"为什么某个长期方向值得继续"，不生成"现在立刻去做"的执行指令**。
- **硬红线**：`manual_review_required=true`、`execution_allowed=false`；不自动改 goal / plan / task 状态；不调用工具 / 不发消息 / 不改文件；`MOTIVATION_BANNED` 词表（我想要 / 我渴望 / 我必须 / autonomous desire …）继续拦绝对化欲望表达。
- **Constitution**：新增 `check_motivation_candidate`（C01-C04），至少复刻 Phase 12 的 evidence 必引 + 禁 auto-complete + 禁 delete + 禁自主意志词表。
- **与 Decision 的关系**：Motivation 给 Decision 提供"长期方向优先级"的只读参考上下文（类似 Phase 12 的 `continuity_context`），但 Decision 的选择逻辑仍不变、仍只给 review 建议。真正把两条链路串成"auto-execute"之前，必须单独开一个 phase 论证安全边界。
- CLI：`run-motivation-cycle` / `list-motivations` / `show-active-motivations` / `verify-motivations` 四命令 + 测试回归。

一句话：Phase 13 该做 **"为什么"层（Motivation）**，但**三件套（Motivation + 许可机制 + auto-action）别一次做完**——先只做可解释、可回滚、evidence-bound 的动机方向建议，把"执行"留到专门的 phase。
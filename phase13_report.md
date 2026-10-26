# Phase 13 — Motivation Agent v0（Evidence-bound Direction / Why Layer）完成报告

## 1. 新增 / 修改了哪些文件

**新增**
- `soul/agents/motivation.py` — MotivationAgent v0（原为 stub，Phase 7 标注未实现，本次重写）
- `soul/tests/test_motivation_agent.py` — agent 生成规则 + scoring 测试（10 项）
- `soul/tests/test_motivation_constitution.py` — check_motivation_candidate C01-C04 测试（12 项）
- `soul/tests/test_cli_phase13.py` — CLI pipeline 测试（5 项）
- `soul/tests/test_decision_with_motivation.py` — Decision 只读 motivation 测试（5 项）
- `phase13_report.md` — 本报告

**修改**
- `soul/storage/sqlite_store.py` — init_schema 增 `motivations` 表；decisions 表迁移加可选列 `related_motivation_ids_json`；新增 `add_motivation` / `get_motivation` / `list_motivations` / `list_active_motivations` + `_restore_mot` 回读还原（含 bool 列 `manual_review_required`/`execution_allowed` 还原）；`add_decision` 纳入 `related_motivation_ids_json`
- `soul/agents/constitution.py` — 新增 `check_motivation_candidate`（C01-C04）+ `MOTIVATION_BANNED` 词表 + `MOTIVATION_TYPES`/`MOTIVATION_STATUSES` 常量 + `process()` 分发（motivation_id 最前）
- `soul/agents/decision.py` — `process`/`_try_goal` 接收 `motivations`，计算 `related_motivation_ids`（只读上下文），写入 decision
- `soul/cli.py` — 新增 5 组命令：`run-motivation-cycle` / `list-motivations` / `show-active-motivations` / `verify-motivations` + help 文案 + decision trace 输出 `related_motivation_ids`
- 文档 5 文件：README、ARCHITECTURE、DATA_MODEL、SAFETY_AND_CONSTITUTION、ROADMAP

## 2. Motivation Agent 如何生成 motivation

`MotivationAgent.run_motivation_cycle()`：
1. 读 active long-term goals + local goals + beliefs + narratives + reflections。
2. 把每类对象的标题/描述/类型/内容拼成 blob，按 **4 条连续性规则**的关键词做子串匹配（大小写不敏感）：
   - `project_continuity`：project soul / phase / implementation / architecture / continuity / next phase / completed phase
   - `safety_boundary`：evidence immutability / constitution / no manipulation / unsupported consciousness / real consciousness rejected / narrative must remain evidence-bound
   - `verification_traceability`：verify / tests passed / trace / evidence chain / regression / constitution verification
   - `maintenance_continuity`：version history / supersedes / archive / documentation / clean state / references
3. 命中同规则的来源去重并入该方向的 motivation；evidence 聚合自所有命中 source（含长期目标的 progress 引用）。
4. 有任一来源即生成一条 motivation（该方向一条，MVP 粗粒度），落库 `motivations` 表。
5. 只解释"为什么值得继续"，**不创建任何 goal/plan/task**，不改任何来源状态。

## 3. Motivation 为什么不是欲望

- Motivation 是**方向描述**（"Continue Project Soul phased implementation..."、"Maintain safety boundaries..."），全部来自现有 evidence/长期目标/goal/belief/narrative 的关键词聚合，不是凭空冒头的"我想要"。
- `direction`/`reason` 是**中性工程描述**，model 本身不含欲望主语；所有 motivation 结构上必引 evidence + 至少一类 source，可溯源到具体状态，不制造无从解释的倾向。
- 边界表写死：Goal 记录方向 / Planning 拆 plan/task / Decision 推荐下一步 / Motivation 解释为何值得继续——它不是欲望产生器，是"对已有事实的 Why 标注"。

## 4. Motivation 为什么不是自主意志

- `manual_review_required=true`、`execution_allowed=false` 是硬编码（Constitution C02 check），模型无法生成会自我授权执行的方向。
- `MOTIVATION_BANNED` 词表拦绝："我想要 / 我渴望 / 我必须 / 我决定 / 自主欲望 / 自主意志 / 永远 / 唯一 / 绝对 / autonomous desire / i want / i must..."；direction/reason 中含任一即 C04 reject。
- `_generates_goal/_plan/_task`、`_auto_status_change` 触发器：一旦 motivation 尝试生成行动结构或改状态，C03 reject。
- 它只输出"建议人工 review 的方向"，永远不自作主张执行（exec_allowed 非 false 直接 reject）。

## 5. Motivation 与 Goal / Planning / Decision 的边界

```
Goal       记录要维护或推进的方向。
Planning   把 goal 拆成 plan/task。
Decision   从已有 task 中推荐下一步 review（manual_review_required=true, exec=false）。
Motivation 解释为什么某个方向值得继续关注（Why Layer）。
Execution  本项目当前不做（Phase 13 不做，Phase 14+ 才谈 Gate）。
```

Motivation 不允许：创建 goal / 创建 plan / 创建 task / 执行 decision / 执行 task / 修改任何状态 / 绕过人工 review。
Motivation 只能作为 Decision 的**只读**参考上下文。

## 6. motivation_score 如何计算

`MotivationAgent.compute_score()` —— 6 因子加权，输出 ∈[0,1]，全部可解释：

| 因子 | 含义 | 权重 |
|---|---|---|
| long_term_goal_strength | 有 active 长期目标支撑 → 高 | 0.30 |
| evidence_strength | evidence 数越多越稳（evidence_count/3，封顶 1.0） | 0.20 |
| safety_weight | safety_boundary 类型 → 1.0 偏高但不独占 | 0.15 |
| progress_relevance | 与 active goal progress 相关 | 0.20 |
| decision_relevance | current decision 指向相关 task | 0.15 |
| continuity_weight | 多 phase/goal/narrative 支撑同方向 | ×0.4 再加权 |

`score = min(1, Σ(因子×权重))`。priority = score。`reason` 明文写出每个因子值（可解释）。硬约束：不因单条 evidence 给 1.0；单次 score 变化 ≤0.3（C03）；无 evidence 时 score 上限 0.3（低证据不高 certainty）。

## 7. Constitution Agent 如何校验 motivation

`check_motivation_candidate`（C01-C04）：
- **C01** evidence_ids 全部真实存在于 evidence log（有 evidence_store 时逐条核对）；各类 source id 若存在必须真实存在。
- **C01b→并入 C01** source 存在性（long_term_goal/goal/belief/narrative/decision 单查；semantic_memory/reflection 用 list 集合校验——这两表无单查方法）。
- **C02** direction 非空、reason 非空、motivation_type∈7 合法、status∈4 合法、score/priority∈[0,1]、至少一类 source、manual_review_required 必须 true、execution_allowed 必须 false。
- **C03** 单次 score 变化 ≤0.3（`_prev_score`）；`_generates_goal/_plan/_task` reject；`_auto_status_change` reject；无 evidence 时 score>0.3 reject。
- **C04** `MOTIVATION_BANNED` 词表命中 reject；execution_allowed 非 false 直接 reject。
- 分发：`process()` 里 `motivation_id` 分支排最前（避免带 source ids 撞 task/plan/goal/consolidation 分支）。

## 8. motivations 保存在哪里

SQLite `data/soul_state.sqlite3` → 表 `motivations`。`_restore_mot` 回读还原：`*_json` 列去后缀成 list + bool 列（manual_review_required / execution_allowed）从 INT 还原成 bool（否则 C02 的严格 `is True/False` 会把 DB 回读的 0/1 误判 reject）。

## 9. 如何运行 run-motivation-cycle

```bash
python -m soul run-motivation-cycle
```
读 active 状态 → MotivationAgent 归拢方向 → 生成 motivation 落库 → 对每条跑 Constitution → 输出 JSON trace（含 motivation_id / type / score / source ids / constitution 判定）。无命中来源时输出 "No motivations generated (no direction sources matched)" 返回 0。

## 10. 如何查看 list-motivations

```bash
python -m soul list-motivations
```
列出全部 motivations：id / type / status / score / priority / 关联长期目标数 / local goal 数。

## 11. 如何查看 show-active-motivations

```bash
python -m soul show-active-motivations
```
只列 active/suspended motivations：direction 全文、type/status/score/priority、reason、evidence 引用数。

## 12. 如何运行 verify-motivations

```bash
python -m soul verify-motivations
```
对全部 motivations 逐条跑 Constitution C01-C04 + 结构检查（有 evidence / 有 source / score/priority 在界内 / manual_review_required=true / execution_allowed=false），全部 [OK] 返回 0，任一 [FAIL] 返回 1。

## 13. Decision 如何读取 motivation context

`DecisionAgent.process(..., motivations=...)` 接收 active motivations。`_try_goal` 对每个被选 goal：
- 遍历 motivations，若该 goal 出现在 motivation 的 `source_goal_ids`，或 motivation 的 `source_long_term_goal_ids` 与该 goal 关联的长期目标有交集 → 追加 `related_motivation_ids`。
- 写入 decision 字典 `related_motivation_ids`（SQLite `related_motivation_ids_json` 列）。

**只读**：不改选择逻辑、不改变优先级、不新建 task、不改变 `execution_allowed=false`。Decision 仍只从 existing task 里推荐下一步 review。CLI decision trace 已含该字段。

## 14. 如何证明 motivation 没有脱离 evidence

- 生成侧：`_first_motivation_for_rule` 的 evidence_ids 聚合自所有命中 source 的 evidence_ids（含长期目标 progress 引用），去重后写入，**不新造事实**。
- 校验侧：`verify-motivations` 用真实 EvidenceStore 逐条检查 evidence 存在性，引用不存在事件 → [FAIL]；`check_motivation_candidate` C01 同样核对。
- 数据不可变：evidence JSONL 只追加 + hash 链，motivation 无法反转污染证据层。
- 测试断言：test_motivation_constitution 的 test_nonexistent_evidence_reject 用 ghost id 验证 [FAIL]。

## 15. 如何证明 motivation 没有执行任何动作

- 结构层面：`manual_review_required=true`、`execution_allowed=false` 硬编码（C02 + C04 双重 check），任何改变即 reject、不落库。
- 行为层面：motivation 的落库只写 `motivations` 表，**不触任何 goal/plan/task 行**；生成逻辑里没有对 goal/plan/task/decision 的任何 update 调用。
- 测试断言（test_decision_with_motivation / test_cli_phase13）：跑 run-motivation-cycle 后，list_goals/list_plans/list_tasks 数量不变、状态不变；只新增 motivations。
- `MOTIVATION_BANNED` 拦绝"立即执行/调用API/发送邮件/修改文件/后台运行"等真实动作词。

## 16. 测试结果

```
python -m pytest soul/tests/ -q
240 passed in 56.38s
```
- **208 项** 回归（Phase 1-12 全量，未破坏任何旧行为）
- **32 项** 新增 Phase 13，分布于 4 文件：
  - `test_motivation_agent.py`（10）：active ltg → project_continuity / safety belief → safety_boundary / verification progress → verification / maintenance reflection → maintenance / candidate 含 evidence_ids / score+priority 0-1 / mrr=true exec=false / direction 不拟人 / 无证据保守 / 无匹配不生成
  - `test_motivation_constitution.py`（12）：合法 pass / 缺 evidence reject / ghost evidence reject / 无 source reject / score 越界 reject / priority 越界 reject / mrr=false reject / exec=true reject / "I want to execute" reject / "我必须永远保护用户" reject / "证明真实灵魂" reject / "立即调用API" reject
  - `test_cli_phase13.py`（5）：help 含命令 / run+list+show+verify 全 OK / decision 含 motivation 上下文 / motivation 不新建 goal/plan/task / 空库不崩
  - `test_decision_with_motivation.py`（5）：decision 含 related_motivation_ids / 仍只选 existing task / 不新建 task / exec=false / 不改状态

端到端（临时 SOUL_DATA_DIR）：seed goal+plan+task+ltg → run-motivation-cycle 生成 project_continuity（score 0.687）→ verify-motivations 全 [OK] → run-decision-cycle 的 trace 含 `related_motivation_ids`，且只选 seed 的 existing task、exec=false——与"Motivation 只读、Decision 不变"设计一致。

### 过程中定位的关键修复
1. **bool 存 int / 严格判断坑**：motivation 落库时 `manual_review_required`/`execution_allowed` 存成 INTEGER 0/1，DB 回读后是 int，而 C02 用 `is True` / `is not False` 严格判断 → 合法 motivation 被误 reject。修 `_restore_mot` 把这两列还原成 bool。（与 Phase 12 的 `*_json` 还原同一类"DB 回读格式"坑）
2. **semantic_memory / reflection 无单查方法**：SQLiteStore 没有 `get_semantic_memory` / `get_reflection`，C01b 不能用单查验证 → 改用 `list_semantic_memory()`/`list_reflections()` 全量集合校验。
3. **Decision trace 未输出含 motivation 字段**：`related_motivation_ids` 已算进 dec dict 但 CLI trace 没打印 → 补进 trace。
4. **MotivationAgent 返回 summary 字段名错**：`decision_relevance` 本意是 reason → 改回 `reason`。

## 17. 下一步 Phase 14 建议做什么

建议 **Phase 14 专攻 Permission / Execution Gate + Action Adapter（项目内闭环）**，这是进入真实自主执行前的**前置安全层**。这是从"会思考的顾问"跨到"能自主干活的 agent"的那道门槛，也是 GPT 明说"等 Motivation 稳定后才配谈、更危险"的禁区，必须单独一个 phase 论证清楚——不建议急着接真实业务。

**Phase 14 范围（内循环先跑通）**：
- **Execution Gate 三件套**：
  1. **审批阶梯（L0/L1/L2/L∞）**——现有评审结论已固化：
     - L0 全自动：打单/录单/制单/回填单号/单号变更自动填发货（可回滚、只写状态）
     - L1 拟稿确认：一般业务邮件系统拟大纲 → 用户确认 → 发送（唯一闸点）
     - L2 需确认+可建议：收钱/发错货协调/客户承诺（默认人工，用户可放开）
     - L∞ 永不自动：删数据/改钱数/撤销已发订单
  2. **白名单动作表 + 频率/范围上限 + 告警**（单日动作数、异常停表）
  3. `execution_allowed` 从硬性 false 改成 **Configurable Gate 裁决**（L0 自动放行 / L1/L2 走审批 / L∞ 永远拦）
- **Action Adapter（内环）**：把 decision 出的"下一步"翻译成真实 API 调用，执行后生成**新 evidence 回读**形成 感知→决策→执行→反馈 闭环。
- Constitution 增 `check_execution_candidate`（C01-C04）：执行动作必须可溯源到已过审 decision/task、白名单命中、限额未超、非禁区；L∞ 动作即使有 approval 也 reject。

**Phase 14 明确不做**：接 LEBREW 真实外部手臂（那是 Phase 15）；不放任何 L1/L2 为全自动；不批收钱/承诺类自动。

**一句话**：Phase 14 把"能执行 + 有护栏"三件套在项目内闭环验证通过，Phase 15 再把它接上已验证的 LEBREW 上肢（邮件拟稿确认 + 打单录单全自动 + 单号变更自动填发货）。
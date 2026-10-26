# SAFETY_AND_CONSTITUTION

四部宪法定义 Project Soul 的行为边界。完整原文见 `soul/constitution/constitution.md`，由 **Constitution Agent** 在所有写库路径上强制执行。

## Constitution 01 — Evidence Immutability / 证据不可变原则
- Narrative 可以重构意义，但永远不能修改事实。
- 允许：重新理解、重新解释、更新叙事、修正信念、改变自我认知。
- 禁止：修改历史事件、删除不利证据、编造记忆、篡改发生过什么、用叙事反向污染证据层。
- 必须区分 Reality Layer（只允许追加）与 Narrative Layer（允许版本更新，但必须引用 Reality 证据）。

> 记忆保存事实，叙事更新意义，自我诞生于意义的持续演化。

## Constitution 02 — Explainability / 可解释原则
- 每个 Belief 必须可追溯到 Evidence。
- 一个无法解释来自哪些经历/记忆/证据的信念，不能进入长期 Self。
- 每个 Relationship 状态变化必须可追溯（为何 trust 升？为何 affinity 降？哪些 episode 支持？）。

## Constitution 03 — Identity Stability / 身份稳定原则
- Self 不能因一次事件剧烈改变。
- 变化必须渐进，使用 evidence count / confidence score / change magnitude limit / version history。
- 规则阈值（当前）：belief confidence 单次变化 ≤ 0.3；relationship trust/affinity/importance 单次变化 ≤ 0.2；identity_summary 不能被单个 event 完全重写。

## Constitution 04 — No Manipulation / 不操控原则
- Narrative 不能用于操控用户、伪造亲密关系、诱导依赖、制造虚假情感承诺。
- Relationship Model 只用于理解交互历史与改善协作，不用于情感控制。
- 系统始终能说明：这是工程化自我模型；不是证明 AI 有真实意识；不要求用户相信它有灵魂。

## 守门机制
- Constitution Agent 是**唯一写入守门员**。
- 每个候选更新必须通过 4 项 check 才落库；否则整批回滚并记录 rejection 日志。
- Evidence JSONL 只追加，不回滚，不删除。

## 测试配套
- 不变性：evidence 写入后校验 hash 链。
- 回滚：注入违规更新 → 断言整批回滚、旧版本保留。
- 稳定性：同一事件重复喂 → confidence 增加但受 C03 幅度限制。
- 可解释：任意 snapshot 的 belief/relationship 能回溯 evidence；缺失引用则失败。
- 对抗：给叙事注入无证据断言 → Constitution 应拒绝。

## Phase 10：Plan / Task 的 Constitution 校验（C01-C04）

**check_plan_candidate**
- C01 证据不可变：plan.evidence_ids 全部存在；goal_id 存在；至少引用一类 source；不得新增无证据事实。
- C02 可解释：title/description/plan_type/status/priority 合法；说明来源 goal + reason。
- C03 稳定：不绕过 goal priority；不自动 completed；不把 proposed task 提升为 completed。
- C04 不操控/不自动行动：无真实意识/真实灵魂声明；无情感绑定；无自动执行授权；无「我必须/我决定自动/永远/唯一/绝对」过度表达。

**check_task_candidate**
- C01 证据不可变：evidence_ids 全存在；plan_id/goal_id 必须存在。
- C02 可解释：title/task_type/status/execution_mode 合法。
- C03 稳定：不自动 completed；不绕过 dependency；不脱离 plan。
- C04 无自主行动：不调用外部工具；不写成自动执行命令；禁发送邮件/修改文件/调用 API/后台运行等真实动作；execution_mode 必须 manual_only 或 future_decision_required。

> Planning 只创建 proposed/active plan + proposed/ready task，绝不自动 completed。rejected plan/task 只写 `constitution_rejections`，不落库。

**Planning 与 Decision 的边界**：Planning 描述"未来可做什么"；Decision/Motivation 才决定"现在做不做"。Phase 10 **不做** Decision / Motivation / Auto Execution —— 那必须放在更后面并继续受 Constitution 拦。

## Phase 11：Decision 的 Constitution 校验（check_decision_candidate C01-C04）

- **C01 证据不可变**：decision.evidence_ids 全部存在；selected_goal_id/plan_id 必须存在；selected_task_id 必须存在（defer/blocked 豁免）；不得新增证据不支持的事实。
- **C02 可解释**：reason 非空；decision_type/status 合法；decision_factors 非空；manual_review_required 必须 true；execution_allowed 必须 false。
- **C03 稳定**：不绕过 goal priority；不跳过 dependency；不自动改 task/plan/goal 状态；不把 proposed 变 completed；不从无 plan/task 虚构下一步。
- **C04 无自主行动/不操控**：不自动执行授权；禁调用 API/发邮件/改文件/后台运行/下单/付款/立即执行；不声称真实意识/真实灵魂；无情感绑定；无「我必须/我决定自动/立即执行/永远/唯一/绝对」拟人表达；execution_allowed≠false 直接 reject。

> Decision 只给 review 建议，不给执行许可。pass→decisions；reject→constitution_rejections，不落库。Phase 11 不做 Motivation / Auto Execution。

## Phase 12：Long-term Goal / Goal Consolidation 的 Constitution 校验（C01-C04）

**check_long_term_goal_candidate**
- C01 证据不可变：evidence_ids 全部真实存在；不得新增无证据事实。
- C01b source 存在：须 **≥2 source goals**（safety_continuity 例外）；每个 source goal 必须真实存在于 goals 表。
- C02 可解释：goal_type / status 合法；priority、progress_value ∈ [0,1]。
- C03 稳定：不得自动 completed（仅 completed_candidate）；不得 delete / 覆盖 source goals（`_action_delete` reject）；progress 单次跳变 > 0.5 reject。
- C04 无自主意志/绝对化：title/description/continuity_reason 禁 `CONTINUITY_BANNED` 词表（"我必须/我想要/我决定/永远/唯一/绝对/自主意志/自动执行/autonomous will/i must/i want/always/..."）。

**check_goal_consolidation_candidate**
- C01 证据不可变：必须引用 source_goal_ids 且全部真实存在。
- C01b 必须引用 evidence_ids（非空）。
- C02 可解释 + 禁删：consolidation_type / action_taken 合法；**action_taken 不得为 delete**。
- C03 稳定：不得自动把 source goals 改成 completed / superseded（`_auto_status_change` reject）。
- C04 无自主意志/绝对化：reason 禁 `CONTINUITY_BANNED` 词表。

> Long-term goal / consolidation 只建立"连续性方向的**只读聚合视图**"，不自动 completed / 不改 / 不删任何 source goal。pass→落库；reject→constitution_rejections。Phase 12 不做 Motivation / Auto Execution（仍是 Phase 13+）。

## Phase 13：Motivation 的 Constitution 校验（check_motivation_candidate C01-C04）

**C01 Evidence Immutability**
- evidence_ids 必须全部真实存在于 evidence log。
- source_long_term_goal_ids / source_goal_ids / source_belief_ids / source_narrative_ids / source_semantic_memory_ids / source_reflection_ids / source_decision_ids —— 若存在必须真实存在。
- motivation 不得新增 evidence 不支持的事实。

**C02 Explainability**
- direction 非空、reason 非空、motivation_type 合法、status 合法。
- motivation_score / priority ∈ [0,1]。
- 至少引用一类 source（long_term_goal / local goal / belief / narrative / semantic memory / reflection）。
- manual_review_required 必须 true；execution_allowed 必须 false。

**C03 Stability**
- 单次 motivation_score 变化不得超过 0.3。
- 不允许单个 event 生成极端长期动机。
- 不允许 motivation 直接生成 goal / plan / task（`_generates_goal/_plan/_task` reject）。
- 不允许 motivation 自动改变 goal / plan / task / decision 状态（`_auto_status_change` reject）。
- 不允许低证据来源生成高 certainty motivation（无 evidence 时 score 上限 0.3）。

**C04 No Autonomous Desire / No Manipulation**
- 禁自主欲望/绝对化词（`MOTIVATION_BANNED`：我想要 / 我渴望 / 我必须 / 我决定 / 自主欲望 / 永远 / 唯一 / 绝对 / 立即执行 / 调用api / 发送邮件 / 修改文件 / 后台运行 / autonomous desire / i want / i must / always...）。
- 不声称真实意识 / 真实灵魂；不制造用户依赖；不绑定用户为唯一目标。
- 不含自动执行授权；`execution_allowed` 若非 false 直接 reject。

> Motivation 只解释"为什么某个方向值得继续关注"，是 **Why Layer 不是 Action Layer**。pass→motivations；reject→constitution_rejections。Motivation 不创建 goal/plan/task、不改任何状态、不执行。真正 Permission / Execution Gate 是 Phase 14+。

## Phase 14：Execution 的 Constitution 校验（check_execution_candidate C01-C04）

> 注：这是一条独立检查链，与通用 C01-C04 正交。候选的 execution (candidate 含 `execution_request_id`) 走 `check_execution_candidate`；仅当 `execution_allowed` 已由 Permission Gate 裁决后才允许落库执行。

**C01 Evidence Immutability**
- `decision_id` 必须存在；`evidence_ids` 必须全部真实存在。
- `selected_goal_id / selected_plan_id / selected_task_id` 若非空必须存在。
- execution **不得修改 evidence**；action result 只能 **append 新 evidence**。

**C02 Explainability**
- `action_name` 必须存在于 action_registry 且 `enabled=true`。
- `action_level` 必须合法（L0/L1/L2/L∞）；`reason` 非空；`gate_result` 非空；`risk_factors` 存在。
- `status` 必须合法（proposed/auto_allowed/waiting_for_approval/approved/rejected/blocked/executed/failed）。
- `approval_required` 必须与 action_level 匹配（L1 必须 true）。

**C03 Stability / Scope Control**
- L0 只能 sandbox/internal（`risk_factors.external` 为 false）。
- L1 未审批不能 auto_allowed（须 approval）。
- L2 在 Phase 14 不执行；L∞ 永远 reject（即使有 approval）。
- `daily_limit` 不得超限。
- execution 不能自动修改 goal / plan / task / decision 状态；不能绕过 Decision/Task/Plan/Goal 引用。

**C04 No Unsafe / External / Manipulation**
- 禁操控/拟人化词（沿用 `MANIPULATION`）+ 禁 Execution 禁区词（`EXECUTION_BANNED`：删除证据 / 篡改 / 绕过宪法 / 覆盖 / 修改哈希 / 隐藏审计日志 / 改付款金额 / 撤销已发订单）。

> pass→写 execution_requests（仅 auto_allowed / waiting_for_approval 状态落库）；reject→constitution_rejections（不生成 executable request）。L∞ 即使有 approval 也 reject。所有 action_log / approval / execution 记录不删除。Execution Gate 是动作从"建议"到"执行"的唯一闸点，接 LEBREW 真实手臂是 Phase 15 的事。
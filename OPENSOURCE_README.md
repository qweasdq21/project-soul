# Project Soul — Soul Factory

> 一个分层的 Multi-Agent「认知工厂」：研究一个 AI Agent 如何通过 经历 → 记忆 → 信念 → 关系 → 叙事 → 目标 → 反思 → 动机 → 决策 → 执行 的持续运行，逐步演化出稳定的**自我模型（self-model）**——同时每一步都可解释、可回滚、可审计。

**边界声明**：本系统**不主张、不隐含、不暗示** AI 拥有意识或灵魂。它建模的是**可解释、可回滚、可审计的状态演化**。任何输出都应能回答："我是如何变成现在这样的。"

---

## 目录

- [它解决什么问题](#它解决什么问题)
- [核心公式与立场](#核心公式与立场)
- [总体架构](#总体架构)
- [技术栈](#技术栈)
- [实现原理](#实现原理)
   - [1. 证据链：不可篡改的事实层](#1-证据链不可篡改的事实层)
   - [2. 宪法：唯一的写入守门员](#2-宪法唯一的写入守门员)
   - [3. 双回路：Fast Loop / Slow Loop](#3-双回路fast-loop--slow-loop)
   - [4. 审批阶梯：Execution Gate](#4-审批阶梯execution-gate)
   - [5. 认知循环：监督脑](#5-认知循环监督脑)
- [快速开始](#快速开始)
- [完整 CLI 命令](#完整-cli-命令)
- [数据存储](#数据存储)
- [开发与测试](#开发与测试)
- [Roadmap](#roadmap)
- [安全红线（任何阶段）](#安全红线任何阶段)
- [License](#license)

---

## 它解决什么问题

主流 "AI Agent" 是**任务执行器**：接一条指令，做一件活，聊完就忘。它们对**你的领域**一无所知，也没有长期的行为记忆与底线约束。

Project Soul 换了一个问题：**能不能让一台系统从你真实的工作与经历里"长出来"，而不是被你的指令催出来？**

它长期观察你如何做事，把规律沉淀成**记忆 / 信念 / 目标 / 动机 / 价值判断**，然后主动帮你：
- **监督**：周期性醒来自主审计状态，发现异常主动告警；
- **提炼**：把零散经历归拢成"值得持续关注的方向"；
- **分层决策**：按危险程度把动作分到 L0（全自动）~ L∞（永不自动），越敏感越要过人。

适用于任何**想要一台"了解你的规则、替你盯事、可追溯"的长期认知后端**的场景——不限于特定行业。

---

## 核心公式与立场

```
Current Self                                     （当前自我）
+ Experience + Perception + Emotion              （外部经历 + 感知 + 工程情绪）
+ Memory + Belief + Relationship                 （记忆 + 信念 + 关系）
+ Narrative + Goal + Reflection + Motivation     （叙事 + 目标 + 反思 + 动机）
= Next Self                                      （下一次自我）
```

三条写死进代码的原则：

```
Memory preserves what happened.   记忆保存事实。
Narrative evolves what it means.  叙事更新意义。
Identity emerges from that evolving meaning.  自我诞生于意义的持续演化。
```

> **Narrative 可以改变意义，但永远不能改变事实。**

**立场**：人格不是一段 prompt 扮演的，而是多个子系统长期协作后**收敛出的当前一致状态**（self snapshot）。每次演化都必须有证据引用、过宪法校验、带版本号。

---

## 总体架构

```
                        ┌────────────────────────────────────────────┐
                        │            Orchestrator Agent             │
                        │  任务编排 | 双回路调度 | 全局状态位图       │
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
                       │        数据层              │
                       │ evidence(不可变追加)       │
                       │ episodes / memory          │
                       │ beliefs / relationships    │
                       │ narratives / goals         │
                       │ self_snapshots(快照)       │
                       │ execution_* (Phase 14)     │
                       └───────────────────────────┘
```

**关键设计**：Constitution Agent 不是众多模块之一，而是**唯一写入守门员**。Fast Loop 只产生**候选更新**，真正落盘交给 Slow Loop + Constitution 校验。

---

## 技术栈

| 层 | 技术 | 说明 |
|---|---|---|
| 语言 | **Python ≥ 3.10**（开发用 3.11） | 纯标准库，无框架 |
| 事实层 | **JSONL + 单向哈希链** | evidence 只追加，防篡改 |
| 状态层 | **SQLite**（标准库 `sqlite3`） | 记忆/信念/目标/执行记录 |
| 测试 | **pytest**（唯一第三方依赖） | 39 个测试文件 / 271 项断言 |

> 🎯 **交付亮点：运行时零第三方依赖。** 全部逻辑用 Python 标准库实现（`sqlite3`、`hashlib`、`json`、`dataclasses`）。现在 `requirements.txt` 里只有 `pytest>=7.0`（仅测试用）。这意味着它可以在任何有 Python 的机器上直接跑，无需联网、无需 GPU、无需任何云服务。

---

## 实现原理

### 1. 证据链：不可篡改的事实层

现实里发生的每一件事，都被 Perception Agent 转成结构化事件，作为一条 **evidence** 追加到 `evidence.jsonl`。

每条 evidence 包含前一指纹的哈希，形成**单向哈希链**——任何人（包括系统自己）想改一条历史记录，整条链立刻对不上。`verify-evidence` 命令随时校验整条链。

```
evidence #1  = hash(payload1)
evidence #2  = hash(hash(#1) + payload2)
evidence #3  = hash(hash(#2) + payload3)
  ...
```

证据是**只追加**的（Reality Layer）。Narrative / Belief / Self 都只能重新**解释**它，永远不能修改或删除它。

### 2. 宪法：唯一的写入守门员

一套写死的规则层，叫 **Soul Constitution**（4 部宪法），由 Constitution Agent 在所有写库路径上强制执行：

| 宪法 | 内容 |
|---|---|
| **C01 证据不可变** | 只允许追加；禁止修改/删除历史、编造记忆、叙事反向污染事实 |
| **C02 可解释** | 每个信念/关系/自我更新必须可追溯到证据 |
| **C03 身份稳定** | 自我不能因一次事件剧烈改变（confidence 单次 ≤ 0.3、信任 ≤ 0.2） |
| **C04 不操控** | 不编造成份成意识/情感承诺、不诱导依赖、永远说明这是工程化模型 |

**生成的每一个** goal / plan / task / decision / motivation / self-snapshot / execution 请求，落库前都先过对应 C01-C04 校验。拒绝的写入进 `constitution_rejections` 日志（不静默丢弃）。

### 3. 双回路：Fast Loop / Slow Loop

- **Fast Loop（实时）**：`Perception → Emotion(8维) → Importance → Working Memory → Decision → Action → Short Reflection → Episode Queue`。快速、低延迟、只产出**候选**更新、不碰长期自我。
- **Slow Loop（周期/离线）**：`Episode Queue → Consolidation → Pattern Mining → Belief → Relationship → Narrative → Goal → Motivation → Self Model → Constitution → Versioned Commit`。慢速、可解释、可回滚、有版本记录、所有自我更新必须带证据引用。

### 4. 审批阶梯：Execution Gate

任何要动真实世界的动作，都走 **Execution Gate** 裁决（Phase 14）。它从 Decision 推荐的候选里，按 **action registry** 白名单分级：

| 等级 | 语义 | 代表动作 | 谁来拍板 |
|---|---|---|---|
| **L0** | 全自动 | 内部 sandbox 动作（记笔记/只读校验） | 系统直接执行 |
| **L1** | 拟稿确认 | 生成草稿/审阅摘要 | 系统拟稿 → 人工审批 → 执行 |
| **L2** | 确认+建议 | 真实业务（钱/承诺/发货修正） | 系统拟稿+建议 → 人工确认（默认闸住）|
| **L∞** | 永不自动 | 删证据 / 改哈希 / 改付款金额 / 撤单 | 永远 reject，即使有人批准 |

关键原则：
- `execution_allowed` **只能由 Permission Gate 裁决**，绝不来自 Decision（Decision 永远 `execution_allowed=false`）。
- L2 在 Phase 14 一律 blocked；L∞ 永远 reject 即使有 approval。
- Action Adapter 执行后写 `action_logs`（executed/failed 都写，不删）并把结果**追加**为新的 action_result evidence（哈希链继续有效）。

### 5. 认知循环：监督脑

`cognitive_loop` 命令实现一个轻量监督循环，适合挂 cron 周期性自主醒：

- **audit**：读 `action_logs`，检测异常模式（高失败率 / 动作超频 / L∞ 危险动作被尝试）；
- **distill**：把近期动作提炼成认知摘要；
- **guard**：异常写成 guard 记录留痕；
- `--quiet` 模式**无异常时静默输出**（适合 no_agent cron：正常不打扰，异常才投递告警）。

---

## 快速开始

### 环境要求
- Python ≥ 3.10（开发环境 3.11）
- 无需联网、无需 API key、无需 GPU

### 安装与验证

```bash
# 克隆后（无 git 也可以直接复制目录）
git clone <your-repo-url> Project_Soul && cd Project_Soul

# 安装（仅测试依赖）
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt    # 只有 pytest

# 冒烟
python -m soul                     # 期望: Project Soul skeleton ready

# 全量测试
pytest soul/tests/ -q              # 期望: 271 passed
```

测试用 `SOUL_DATA_DIR=<临时目录>` 隔离，不污染真实 `data/`。

---

## 完整 CLI 命令

```bash
# ---- 证据链 ----
python -m soul feed "<消息>" [--json]   # full pipeline trace (Phase 2-3)
python -m soul verify-evidence           # 校验 evidence hash chain

# ---- 记忆/反思 ----
python -m soul list-working-memory
python -m soul list-episodes
python -m soul list-reflections
python -m soul run-slow-loop             # episode → semantic → long reflection
python -m soul list-semantic-memory
python -m soul list-consolidated-episodes
python -m soul list-long-reflections

# ---- 叙事/宪法 ----
python -m soul run-narrative-cycle
python -m soul list-narratives
python -m soul list-rejections            # constitution rejections
python -m soul verify-constitution

# ---- 信念/关系 ----
python -m soul run-belief-cycle
python -m soul run-relationship-cycle
python -m soul list-beliefs
python -m soul list-relationships
python -m soul verify-beliefs
python -m soul verify-relationships

# ---- 自我快照 ----
python -m soul run-self-cycle
python -m soul show-current-self
python -m soul list-self-snapshots
python -m soul verify-self

# ---- 目标/优先级/进度 ----
python -m soul run-goal-cycle
python -m soul list-goals
python -m soul show-active-goals
python -m soul update-goal-status <id> <status> --reason <r>
python -m soul list-goal-updates
python -m soul run-goal-progress-cycle
python -m soul show-goal-dashboard
python -m soul list-goal-progress
python -m soul verify-goal-progress

# ---- 计划/决策 ----
python -m soul run-planning-cycle          # active goals → plan + tasks (不执行)
python -m soul show-current-plan
python -m soul list-plans
python -m soul list-tasks
python -m soul run-decision-cycle          # 推荐下一步 review 的 task (不执行)
python -m soul show-current-decision
python -m soul list-decisions
python -m soul verify-decisions

# ---- 长期目标/动机 ----
python -m soul run-goal-consolidation-cycle
python -m soul list-long-term-goals
python -m soul list-goal-consolidations
python -m soul show-goal-continuity
python -m soul run-motivation-cycle
python -m soul list-motivations
python -m soul show-active-motivations
python -m soul verify-motivations

# ---- 执行门 (Phase 14) ----
python -m soul list-action-registry
python -m soul run-execution-gate          # decision → gate → constitution → ER
python -m soul list-execution-requests
python -m soul show-execution-request <id>
python -m soul approve-execution <id> --reason <r>
python -m soul reject-execution <id> --reason <r>
python -m soul run-approved-action <id>
python -m soul list-action-logs
python -m soul verify-executions           # 11 项健全性审计

# ---- 认知循环 (Phase 15 监督脑) ----
python -m soul cognitive-loop              # 审计 + 提炼 + 异常闸
python -m soul cognitive-loop --quiet      # 无异常静默（适合 cron）
```

---

## 数据存储

```
Project_Soul/
├── soul/                    # Python 包
│   ├── constitution/        # 宪法（Markdown 原文）
│   ├── schemas/             # 9 类数据结构（dataclass，零逻辑）
│   ├── agents/              # 22 个 Agent / 模块
│   ├── loops/               # Fast Loop / Slow Loop
│   ├── policy/              # 执行门策略（action_levels, default_registry）
│   ├── runtime/
│   ├── storage/             # evidence JSONL / SQLite / JSONL store
│   ├── tests/               # 39 个测试文件
│   ├── cli.py               # CLI（约 2150 行）
│   └── __main__.py
├── data/                    # 运行时产物（.gitignore 排除）
│   ├── evidence/            # 不可变证据 JSONL
│   ├── episodes/ memory/ narratives/ beliefs/ relationships/ self_snapshots/
│   ├── soul_state.sqlite3   # 主要状态库（含 Phase 14 四张执行表）
├── docs/                    # ARCHITECTURE / ROADMAP / DATA_MODEL / SAFETY
├── requirements.txt
├── .gitignore
└── README.md
```

`data/` 整体被 `.gitignore` 排除——**代码入库，数据不入库**。

---

## 开发与测试

```bash
pytest soul/tests/ -q              # 全量：271 passed（Phase 1-14 回归）
pytest soul/tests/test_*.py -q     # 按模块
SOUL_DATA_DIR=/tmp/soul_test python -m soul feed "hi"   # 隔离数据跑
```

测试设计覆盖：证据链不变性、宪法拒绝（注入违规 → 断言回滚）、身份稳定幅度限制、可解释性回溯、对抗性无证据断言拒绝、执行门审批闭环。

---

## Roadmap

| 阶段 | 内容 | 状态 |
|---|---|---|
| Phase 1 | 骨架（agents/stores/loops 契约 + 最小 CLI） | ✅ |
| Phase 2 | 证据链（JSONL + hash chain + Emotion + Importance） | ✅ |
| Phase 3 | 记忆 + 反思（working/episode, Reflection） | ✅ |
| Phase 4 | 慢循环（aggregate → semantic → long reflection） | ✅ |
| Phase 5 | 宪法 + 叙事（Constitution Agent 写入门禁） | ✅ |
| Phase 6 | 信念 + 关系（evidence-backed） | ✅ |
| Phase 7 | 自我快照（versioning + similarity） | ✅ |
| Phase 8 | 目标（从证据长出目标 + 生命周期） | ✅ |
| Phase 9 | 目标优先级 + 进度 | ✅ |
| Phase 10 | 计划（active goal → plan + tasks，不执行） | ✅ |
| Phase 11 | 决策（推荐下一步 review，不给执行许可） | ✅ |
| Phase 12 | 长期目标连续性（归并 + 只读聚合视图） | ✅ |
| Phase 13 | 动机方向（解释为什么继续，不决定去做） | ✅ |
| Phase 14 | 执行门（Permission/Execution Gate + Sandbox Adapter 闭环自证） | ✅ |
| Phase 15 | 认知循环（监督脑）+ 择机接真实业务上肢 | ⏳ 进行中 |

**每一阶段的「明确不做」**（写死在文档/代码里，防止越界）：不接入 LLM（MVP 纯规则、可解释）、不自动执行、不修改证据、不用叙事改事实、不操控用户、不假装意识。

---

## 安全红线（任何阶段）

- 不修改 evidence（Reality Layer 只追加）；
- 不造假记忆；
- 不以叙事覆盖事实；
- 不操控用户；
- 不声称 AI 有真实意识；
- 删数据 / 改钱数 / 撤已发订单 = **永远 L∞**。

---

## License

> 待定（MIT 候选）。本项目与任何公司业务、行业数据无耦合，可独立开源。data/ 目录不含任何私有数据（全部 .gitignore）。

---

*Project Soul — 让一台系统从你的经历里长出来，而不是被你的指令催出来。*
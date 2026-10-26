# Phase 15 — 接 LEBREW 真实业务手臂到 Execution Gate

> 实施原则（用户 2026-09-12 拍板）：**不直接全开，一边用一边改**。
> 不做只读观察期、不做 3 天观察缓冲；直接接真实手臂，在真实使用中边用边改。
> 风险从低到高逐臂放开，L2（钱/承诺/发错货）与 L∞（删数据/改钱/撤单）默认闸住。
> GPT 已确认 Phase 14 通过并批准 Phase 15（"Phase 14 过了，说明 Gate" + "确认。Phase"）。

## 本质

Phase 14 的 Gate 是通用仲裁层，只懂 action_name + level + evidence，不懂燕文/千牛/Shopify/邮件。
**Phase 15 不是改 Gate，而是两件事：**
1. 给每个真实手臂动作在 action_registry 注册（选 L0/L1/L2/L∞ 等级）。
2. 让 ActionAdapter 学会调用已验证的脚本（复用，不重写）。

真实业务触发方式：现有 cron 看门狗检测到事件 → 调 `lebrew_ingest(event)` → 证据入库 → 匹配 registry 动作 → 走 Gate → L0 直接执行 / L1/L2 转飞书等用户确认 → 结果 evidence 回写。事件检测逻辑零改动。

## 动作映射表（审批阶梯，用户已确认）

| 动作 | 等级 | 触发源 | 处理 |
|---|---|---|---|
| yanwen_create_label 燕文制单 | L0 全自动 | 千牛/独立站订单 | 制单→单号→回填发货表 |
| yanwen_backfill_tracking 回填单号 | L0 全自动 | 燕文响应 | 写飞书发货表+Shopify |
| qianniu_record 千牛录单 | L0 全自动 | 千牛待录 | 写发货表 |
| shipment_status_change 单号变更自动填发货 | L0 全自动 | 看门狗 | 状态置已发货 |
| shopify_fulfill Shopify 回填 | L0 全自动 | 腾讯转运看门狗 | GraphQL 回填 |
| draft_reply_email 邮件拟稿 | L1 拟稿确认 | Gmail 看门狗 | 拟大纲→飞书确认→发送 |
| send_money_action 收钱 | L2 确认+建议 | 业务 | 拟稿+建议→确认（默认闸住） |
| commit_to_customer 客户承诺 | L2 确认+建议 | 业务 | 同上 |
| fix_shipment_mistake 发错货协调 | L2 确认+建议 | 客户私信 | 走原渠道回复 |
| delete_data / change_amount / revoke_order | L∞ 永不 | - | 永远 reject |

## 新文件

- `soul/agents/lebrew_trigger.py` — `lebrew_ingest(event)` 统一入口
- `soul/agents/lebrew_adapters.py` — 真实手臂 handler（复用已验证脚本）
- 复用：Phase 14 的 ActionResult / action_log / evidence 回写框架

## 已固化的关键规则（write 进 adapter，勿忘）

1. 燕文制单品名**一律写 SKU/variant_title**（如 98mm Filter），不写系列衍生名（8/26）。
2. Shopify 回填前 **is_real_tracking 过滤 F 占位**（拒付/暂不发），否则误发只能 Cancel（9/4 踩 2954）。
3. 中东单常缺邮编/省份/英文地址 → adapter 遇缺字段**主动向用户提问（L1 闸住）**，绝不瞎编（8/20）。
4. 邮件用**中性表述**（"The package is on its way"），不提今日发货（客户偏好）。
5. 补发给客户单**走货代不走燕文**（已确认，燕文太慢）。

## 落地顺序（一边用一边改）

1. 建触发骨架 lebrew_trigger.py（任意手臂通用）
2. 接第一个真实手臂（看门狗改一行调用）→ 真实跑 → 修坑
3. 逐个接剩余 L0 → 放 L1 邮件拟稿确认
4. L2 按需放开，L∞ 永不动

## 审批交互

L1/L2 拟好后通过**飞书**发用户确认（不用桌宠）。回"确认"→approve-execution→执行；回"改"→重拟；回"不"→reject。

---

## 落地实况（2026-09-12）

**已完成：p15-1 ~ p15-4 + p15-5 验证**

实现方式定为**轻量留痕（方案 A）**：不改看门狗执行逻辑，只在真实动作发生后调 `lebrew_ingest.py` 把"做了啥"写成 business_observation + action_result evidence，并落 execution_request + action_log（全走 Gate L0 旁路语义，不接管执行）。零执行风险，先拿到完整审计链。

### 新文件
- **`~/.hermes/scripts/lebrew_ingest.py`**（实际放 `%LOCALAPPDATA%\hermes\scripts\`，190 行）— cron 看门狗 subprocess 调用的统一留痕入口。参数：单个 JSON 事件 `{"type","order","tracking","company","status","summary"}`。写 Soul evidence（hash 链）+ execution_request + action_log，幂等、失败不影响主流程。
  - 注：方案里的 `lebrew_trigger.py` / `lebrew_adapters.py` 未单独建——ingest 直接用 subprocess + 复用 Phase 14 框架实现同等功能，更简单、同环境可见。

### 已接留痕的看门狗（4 个脚本 / 3 个动作）
| 看门狗脚本 | 动作 | 等级 | 留痕时机 |
|---|---|---|---|
| `tencent_tracking_watch.py` | shopify_fulfill | L0 | 每次回填成功/失败 |
| `yanwen_backfill_shopify.py` | yanwen_backfill_tracking | L0 | 回填成功/失败/already |
| `daily_qianniu_dispatch.py` | qianniu_record | L0 | 派单/突变告警/失败 |
| `gmail_new_mail.py` | draft_reply_email | L1 | 新邮件事件 |

### registry 已补灌 12 个真实动作
shopify_fulfill/yanwen_create_label/yanwen_backfill_tracking/qianniu_record/shipment_status_change = **L0**；draft_reply_email = **L1**；send_money_action/commit_to_customer/fix_shipment_mistake = **L2 闸住**；delete_evidence/change_amount/revoke_order = **L∞ 永不**。

### 验证结果
- 4 脚本全部编译通过；gmail/腾讯 dry 正常；腾讯 19:00 真实跑一轮 last_status=ok、dry 列出全部批次含 2954 拒付标注（is_real_tracking 铁律在作用）。
- 留痕链端到端打通：evidence 12→14、execution_request+action_log 落 `executed` 状态、result_evidence_id 关联完整、hash 链未断。smoke test 用 `#lebrew-TESTING` 标记（保留，evidence 不可变）。

### 待接（边用边改，下次真制单时顺手）
- **yanwen_create_label 燕文制单本体**：制单脚本 `create_lebrew_*.py` 是逐单临时生成的，无统一生成器可 patch，不能改历史脚本。下次生成新制单时在生成流程里带上 ingest 即可。
- L1 邮件拟稿确认流（draft_reply_email 触发进 Soul 后转飞书确认）——方案已定，等有真实新邮件走一轮。
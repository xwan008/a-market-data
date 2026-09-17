# A股低风险买点榜｜预筛与深度研究范围 Override

本文件只覆盖 `RUNTIME_READ_PROTOCOL.md` / `SKILL.md` 中关于 routed company universe 全量深度研究、Top N 禁止、Transmission coverage 范围和发布漏斗的规则。与它们冲突时，本文件优先；Trend Handoff 的行业路由入口仍同时遵循 `TREND_HANDOFF_ROUTING_OVERRIDE.md`。

## 1. 目标

将买点榜拆成两层：

```text
Trend Handoff
→ 三级行业展开全部策略主板公司
→ 公司级硬过滤
→ 轻量同业预筛
→ 每个三级行业原则上 Top 5（明确并列可 6）
→ 深度研究：Transmission → Expectation → Risk–Reward
```

预筛只分配深度研究资源，不构成投资结论、买卖建议或最终排名。

## 2. 公司级硬过滤

对每个已解析三级行业，先通过 `data/research/company_industry_index.json` 展开当前策略主板 universe 的全部公司，并从 `data/shards/<股票代码前5位>.json` 读取当前正式收盘数据。

仅允许以下公司级硬条件：

- ST；
- 价格缺失、非数值或 <= 0；
- 净利润缺失或 <= 0；
- 关键估值、财务或趋势结构数据缺失；
- 营收同比 < -20% 且净利润同比 < -50%；
- 其他已在正式协议中明确的公司级数据完整性硬条件。

禁止使用三级行业的 `trend / strength / breadth / confidence / buyability` 做任何准入或排序。

## 3. 轻量同业预筛

轻量预筛只使用仓库当前正式收盘事实，不做公司公告、新闻、研报或 Web 深度研究。

### 3.1 基础字段

每家公司定义：

- `core_profit_yoy`：优先 `deduct_basic_eps_yoy`，缺失时回退 `net_profit_yoy`；
- `non_core_eps_share_pct`：若 `basic_eps` 与 `deduct_basic_eps` 均可用，则 `abs(basic_eps - deduct_basic_eps) / max(abs(basic_eps), 0.01) * 100`；否则记为不可用；
- `cashflow_positive`：`operating_cashflow_per_share > 0`；
- `valuation_metric`：优先正数 `pe_ttm`，其次正数 `pe_dynamic`，再次正数 `pb`；
- `position_pct`：使用 60 日价格结构中的当前位置百分位。

### 3.2 同行业百分位分量

在同一个三级行业、通过硬过滤的公司之间计算 0–1 百分位：

- `revenue_growth_pct`：`revenue_yoy` 越高越优；
- `core_profit_growth_pct`：`core_profit_yoy` 越高越优；
- `valuation_attractiveness`：可用正估值越低越优；
- `price_crowding_attractiveness`：`position_pct` 越低越优。

质量分量：

```text
quality = 0.5 * cashflow_score + 0.5 * one_off_score
```

其中：

- `cashflow_score = 1` 若经营现金流/股 > 0，否则 0；
- `one_off_score = 1` 若 `non_core_eps_share_pct` 可用且 < 20%；
- 若该字段不可用，`one_off_score = 0.5`；
- 若 `non_core_eps_share_pct >= 20%`，`one_off_score = 0`。

预筛分数：

```text
transmission_proxy = 0.5 * revenue_growth_pct + 0.5 * core_profit_growth_pct
pre_screen_score =
    0.40 * transmission_proxy
  + 0.25 * quality
  + 0.20 * valuation_attractiveness
  + 0.15 * price_crowding_attractiveness
```

该分数仅用于决定谁进入深度研究，不得直接映射为 READY / WAIT / UNCERTAIN / DROP。

## 4. 每行业深度研究名额

1. 每个三级行业按 `pre_screen_score` 从高到低排序；
2. 原则上选择前 5 家进入深度研究；
3. 若通过硬过滤的公司 <= 5 家，则全部进入；
4. 只有当第 6 名与第 5 名 `pre_screen_score` 的绝对差 <= 0.03 时，允许把第 6 名作为明确并列一并进入；
5. 单个三级行业深度研究上限为 6 家，不再继续扩展；
6. 同一公司若被多个 trend signal / industry route 命中，只研究一次，但保留全部来源趋势上下文。

## 5. PRE_SCREENED_OUT 语义

通过公司级硬过滤、但未进入本行业 Top 5/并列第 6 的公司，记录：

```text
pre_screen_status = PRE_SCREENED_OUT
```

`PRE_SCREENED_OUT` 表示“本轮未分配深度研究资源”，不是基本面否定：

- 不得计入 `DROP`；
- 不执行 Transmission / Expectation / Risk–Reward；
- 不进入 READY / WAIT / UNCERTAIN / DROP 统计；
- 至少保存 code、name、industry_code、industry、pre_screen_score 和被截断原因。

## 6. Coverage

正式版 coverage 分两层：

### 6.1 Pre-screen coverage

```text
pre_screen_processed_codes == all_hard_eligible_routed_company_codes
```

即所有三级行业展开并通过公司级硬过滤的公司，都必须完成轻量预筛或明确记录无法计算原因。

### 6.2 Deep research coverage

```text
deep_research_company_codes
= 每个三级行业 Top 5 + 明确并列第 6 的精确去重并集
```

随后：

- `transmission_coverage` 只要求覆盖 `deep_research_company_codes`；
- `expectation_coverage` 覆盖其中所有 Transmission=SUPPORTED 公司；
- `risk_reward_coverage` 继续按正式协议覆盖 EARLY / CONFIRMING / 新预期重置，以及 PRICED_IN / EXHAUSTED 的 WAIT_EXPECTATION 闭合。

因此，不再要求对行业内所有硬过滤合格公司做 Transmission 深度研究。

## 7. 正式发布 Gate

正式版只有同时满足：

```text
runtime_hard_gate = PASSED
trend_handoff_gate = PASSED
routing_coverage = COMPLETE
pre_screen_coverage = COMPLETE
transmission_coverage = COMPLETE
expectation_coverage = COMPLETE
risk_reward_coverage = COMPLETE
publication_ready = true
```

才允许覆盖 `research/latest_formal_result.json`。

## 8. 正式结果与漏斗

正式结果新增/保留：

- `pre_screen_selected`：进入深度研究的公司；
- `pre_screened_out`：通过硬过滤但未入选深研的公司；
- `hard_filtered_out`：未通过公司级硬条件的公司及原因；
- `ready / wait / uncertain / drop`：只统计深度研究后的最终状态。

漏斗至少记录：

- trend signals total / resolved / unresolved；
- routed industries；
- routed universe company count；
- hard-eligible company count；
- hard-filtered-out count；
- pre-screen selected count；
- pre-screened-out count；
- Transmission SUPPORTED / UNCERTAIN / NOT_SUPPORTED；
- Expectation EARLY / CONFIRMING / PRICED_IN / EXHAUSTED / UNCERTAIN；
- READY / WAIT / UNCERTAIN / DROP。

## 9. 研究纪律

- 预筛阶段不得调用 Web 深度研究；
- 深度研究阶段仍优先公司公告、交易所披露、正式财报、投资者关系记录等一手证据；
- Top 5 是研究资源上限，不是投资排名；
- 若预筛字段不足以稳定排序，应记录预筛不确定，而不是主观补齐；
- 不得因为已找到 READY 提前停止已入选深度研究公司的完整 coverage。

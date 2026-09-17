# A股低风险买点榜｜运行时执行协议

本文件是唯一正式执行契约。只描述当前有效流程，不保留历史版本分支。

## 1. 正式输入

### 1.1 19:00 / 手动正式版

读取当前 `main`：

- `skill/RUNTIME_READ_PROTOCOL.md`
- `skill/SKILL.md`
- `data/runtime/meta.json`
- `data/research/industry_state.json`
- `meta.screening_group_index_file`
- Stage 0 选中行业对应的 `screening_groups_by_industry/<industry_code>.json`

`meta.screening_group_file` 是完整审计视图；Stage A 只读取选中行业的 per-industry shard。

每次正式触发都是新的独立事务，不复用上一轮 Stage A / Gate / Deep Research 结论。

### 1.2 07:00 早间版

读取：

- `skill/RUNTIME_READ_PROTOCOL.md`
- `research/latest_formal_result.json`
- 当前最新有效正式收盘 `data/runtime/meta.json`（仅校验 trade_date / runtime 身份）

早间版不重新选股。

---

## 2. Bootstrap / Runtime Hard Gate

19:00 / 手动正式版必须确认：

- `runtime_validation.status == passed`；
- snapshot 为当前最近有效正式收盘；
- meta 可解析；
- `screening_group_validation.status == passed`；
- `screening_group_industry_shard_validation.status == passed`；
- candidate、完整 screening view、industry shards 股票全集一致；
- candidate code 唯一；
- YoY 单位为 `percentage_points`；
- `industry_state.json` 可解析、`status == valid`、trade date 与正式收盘一致；
- `industry_state.buyability_context.status == valid` 且 `buyability_context.trade_date` 与正式收盘一致。

研究准入只包括：

- 非 ST；
- price 为有效正数；
- `net_profit > 0`；
- report / valuation context / 20日以上趋势 / 60日结构数据完整；
- 不满足“收入同比 < -20 且净利润同比 < -50”的严重经营恶化条件；
- 行业属于盈利/可研究行业池。

只有客观 Hard Gate 失败才允许整轮 FAILED。候选多、研究工作量大、某阶段尚未完成，都不是失败理由。

---

## 3. Stage 0｜景气 + 资金 + 可买性，动态选择 3–5 个行业

Stage 0 以 `data/research/industry_state.json` 为行业判断源，不做全行业公开研究。

盈利/可研究行业资格：

```text
trend == improving
OR
(trend == stable AND breadth in {broad, divergent})
```

只有先进入上述资格池的行业才参与排序。排序同时使用三类证据：

### 3.1 景气 / 盈利改善

- `trend`
- `strength`
- `breadth`
- `confidence`
- `core_improving_breadth`
- `aggregate_revenue_yoy`
- `aggregate_parent_profit_yoy`

### 3.2 资金 / 市场确认

- `market_confirmation`
- `market_activity`
- `market_breadth`
- `market_metrics.breadth_score`
- `market_metrics.median_volume_ratio_vs_20d`
- `market_metrics.expanding_volume_share`
- `market_metrics.day_up_ratio`
- `market_metrics.strong_up_ratio`
- `market_metrics.five_day_up_ratio`

### 3.3 可买性 / 拥挤度

读取每个行业的 `buyability`：

- `buyability.label`
- `buyability.score`
- `buyability.components.valuation_attractiveness`
- `buyability.components.price_attractiveness`
- `buyability.components.earnings_support`
- `buyability.metrics.median_positive_pe`
- `buyability.metrics.median_60d_position_pct`
- `buyability.metrics.median_20d_change_pct`
- `buyability.metrics.median_core_profit_yoy`
- `buyability.metrics.core_profit_positive_share`
- `buyability.metrics.median_roe`
- `buyability.metrics.positive_operating_cashflow_share`

`buyability` 只用于行业入口排序，不是行业或个股硬门。目标是避免把“景气最强 + 资金最热”机械等同于“低风险买点最多”。

排序原则：

1. 景气恶化行业不能仅凭便宜进入资格池；
2. 资金很强但 `buyability` 明显 stretched 的行业，应相对降序；
3. 景气改善仍成立、资金已有确认，同时 `buyability` 更 favorable / balanced 的行业，应相对前移；
4. 不要求三个维度同时最强，也不做固定行业类型配额；
5. 不以单个 PE、单个价格位置或单个可买性分数决定行业去留；
6. 目标是寻找“基本面改善仍在、市场开始确认、但价格与估值尚未普遍透支”的行业。

形成有序行业候选序列后，再读取 `meta.screening_group_index_file` 中对应行业的 `candidate_count`，只用于决定入口宽度：

1. 先选择有序候选中的前 3 个行业；
2. 计算这 3 个行业的 runtime candidate 合计；
3. 若合计 `< 30`，加入第 4 个行业；
4. 若加入第 4 个后合计仍 `< 30`，加入第 5 个行业；
5. 一旦合计 `>= 30` 或已选择 5 个行业，立即停止扩展。

因此正式 `selected_industry_codes` 数量为 3–5 个。若合格行业不足 3 个，则按实际数量执行并明确记录原因。

若某个高排序行业在 index 中 `candidate_count == 0`，其计数按 0 处理；动态扩展仍按上述规则继续，最多到第 5 个行业，不再向后无限补位。

固定 `selected_industry_codes` 后行业层结束。后续公司判断只使用公司事实与必要的行业传导事实，不再追加新的行业入口门槛。

---

## 4. Stage A 工作视图｜只读取选中行业 shards

Stage 0 完成后：

1. 根据 `meta.screening_group_index_file` 找到每个 `selected_industry_code` 对应 shard；
2. 只读取这 3–5 个完整 industry shard；
3. shard 较长时按其 `line_count` 使用 40 行有界区间完整读取；
4. 一个申万三级行业组不可拆成不同判断批次。

若某 selected industry 在 index 中没有 runtime candidate，记录 `NO_RUNTIME_CANDIDATE`；这不是 FAILED。

Stage A universe 必须等于选中行业 shards 中全部候选的并集。

---

## 5. Fresh Transaction / Frozen Ledger

每次触发生成新 `run_id`。

`research/pre_research_ledger.json` 只用于当前 invocation：

1. 先写 `BUILDING`；
2. 记录本轮正式文件 blob SHA、trade_date、selected_industry_codes；
3. 完成 selected industries 全部 Stage A 后一次性写 `FROZEN`；
4. 下一次触发必须重建，不得 resume。

Stage A 期间禁止公司级外部 Web 研究。

---

## 6. Stage A｜Structured Screening

处理 selected industries 的全部 runtime candidates。

对每个行业完整执行：

1. `PEER_DOMINATED`；
2. 未被支配者进入 `CLEARLY_WEAK / PASS_TO_DEEP_RESEARCH / UNCERTAIN`；
3. 每只公司恰好一个 ledger entry；
4. 不得 Top N、不设行业配额、不因为已有好公司提前停止；
5. Stage A 防漏优先。

Stage A 使用的事实包括价格结构、估值、盈利质量、现金流、行业到公司的传导等。任何单一指标都不足以替代综合判断；多个彼此独立且方向一致的负向事实可以支持 `CLEARLY_WEAK`。

完成条件：

```text
stage_a_processed_codes == selected_industry_runtime_candidate_codes
```

冻结 Ledger 后派生：

```text
deep_read_codes = PASS_TO_DEEP_RESEARCH + UNCERTAIN
```

---

## 7. Stage B｜Research Worthiness Gate

Frozen Ledger Hard Gate 通过后，对全部 `deep_read_codes` 按 `SKILL.md` 执行：

```text
Q1 核心盈利可信度
→ Q2 安全边际粗筛
→ 必要时 Q2-lite
→ deep_research_required_codes
```

Gate 是研究预算分配，不是排名。不得引入 Top N、行业配额或额外相对排名。

Gate coverage 必须完整闭合。

---

## 8. Deep Research

必须穷尽 `deep_research_required_codes`。

允许分 batch，但 batch 只用于执行，不具有排名或淘汰意义。

公司终态只允许：

- `confirmed`
- `waiting_for_entry`
- `research_uncertain`
- `excluded`

研究逻辑成立但当前价格不满足低风险条件时进入 `waiting_for_entry`。

coverage 未闭合时不得主动结束或发布正式榜。

---

## 9. Unified Entry Evaluation / Risk Cluster / 价格纪律

完全按 `SKILL.md`：

- 正常化盈利区间；
- 可辩护的保守估值；
- conservative fair value；
- `conservative_upside` 原则上 `>= 15%`；
- 当前价原则上距离最终安全区约 5% 以内，或存在同等可量化下行保护；
- Risk Cluster 只在 Stage B 与 Deep Research coverage 完成后做发布层去相关；
- 不反向修改公司研究状态。

正式输出：

```text
股票｜行业｜状态｜当前价｜合理买入区间｜低风险买入区间｜失效价/条件｜第一阻力位｜核心逻辑｜核心风险
```

无可靠低风险区间写 `N/A`，不得制造价格。

---

## 10. 正式输出与漏斗

### A.【今日行业入口】

```text
行业｜景气/盈利摘要｜资金确认摘要｜可买性摘要｜为什么进入今日入口
```

输出本轮动态选中的 3–5 个行业，并明确说明三维证据如何共同支持入口排序。

### B.【A股低风险买点榜】

按当前低风险流程输出。

### C.【筛选漏斗】

至少给出：

- `industry_state` 行业总数；
- 盈利/可研究行业池数量；
- selected industries 数量；
- selected industries 对应 runtime candidate 数；
- Stage A PASS / UNCERTAIN 数；
- Gate 后 Deep Research 数；
- confirmed / waiting / uncertain / excluded 数。

---

## 11. 正式结果持久化｜19:00 / 手动正式版成功后的唯一交接

唯一正式交接文件：

```text
research/latest_formal_result.json
```

只有同时满足：

```text
runtime_hard_gate = PASSED
stage_a_coverage = COMPLETE
stage_b_gate_coverage = COMPLETE
deep_research_coverage = COMPLETE
publication_ready = true
```

才允许写入/覆盖。

FAILED / INCOMPLETE / UNVERIFIED / coverage 未闭合的运行绝不能覆盖上一份 COMPLETE 文件。

文件至少包含：

- `schema_version`
- `result_kind = a_share_low_risk_formal_result`
- `status = COMPLETE`
- `trade_date`
- `run_id`
- `published_at`
- `source_runtime_trade_date`
- `source_runtime_commit_sha`
- `selected_industries`（保存景气、资金与可买性摘要）
- `confirmed`
- `waiting_for_entry`
- `research_uncertain`
- `excluded`
- `funnel`

每个 confirmed / waiting 至少保存 code、name、industry、status、current_price、reasonable_price_range、low_risk_buy_range、invalidation、first_resistance、primary_profit_driver、dominant_risk_factor、core_logic、core_risk。

写入后必须立即回读校验；并发冲突时不得覆盖更晚 COMPLETE 结果。

---

## 12. 07:00 早间版｜只做隔夜检查

首先读取 `research/latest_formal_result.json`，要求：

```text
result_kind == a_share_low_risk_formal_result
status == COMPLETE
trade_date == 当前最新有效正式收盘 runtime.trade_date
source_runtime_trade_date == trade_date
selected_industries 可解析且通常为 3..5
confirmed / waiting_for_entry 可解析
```

若缺失、EMPTY、非 COMPLETE、结构损坏或 trade_date 不一致：

```text
MORNING_HANDOFF_UNAVAILABLE
```

不得从 runtime candidates 重新推测昨日行业或股票。

若交接有效，只围绕上一份 COMPLETE 的 selected industries、confirmed、waiting_for_entry 检查隔夜商品/价差、海外同行、美元指数、美10Y、Nasdaq/半导体、中国资产海外表现、重大政策/公告/产业突发是否改变昨日计划。

输出只允许：

- `NORMAL`
- `CAUTION`
- `RISK_OFF`

早间版不得新增股票、不得生成新的 selected industries、不得重算完整估值、不得把 waiting 自动升级为 confirmed。

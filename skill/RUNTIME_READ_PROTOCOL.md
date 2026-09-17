# A股低风险买点榜｜运行时执行协议

本文件是唯一正式执行契约。买点榜不再重新选择行业；趋势榜负责发现趋势，行业代码只负责把趋势路由到现有申万三级公司池。

## 1. 正式输入

### 1.1 19:00 / 手动正式版

读取当前 `main`：

- `skill/RUNTIME_READ_PROTOCOL.md`
- `skill/SKILL.md`
- `research/trend_handoff.json`
- `data/runtime/meta.json`
- `meta.screening_group_index_file`
- handoff 中所有已解析 `industry_codes` 对应的 `screening_groups_by_industry/<industry_code>.json`

每次正式触发都是新的独立事务，不复用上一轮 Transmission / Expectation / Risk–Reward 结论。

### 1.2 07:00 早间版

只读取：

- `skill/RUNTIME_READ_PROTOCOL.md`
- `research/latest_formal_result.json`
- 当前最新有效正式收盘 `data/runtime/meta.json`（校验 runtime 身份）

早间版不重新路由公司，不重新研究新股票。

---

## 2. Bootstrap / Hard Gate

19:00 / 手动正式版必须确认：

- `runtime_validation.status == passed`；
- `screening_group_validation.status == passed`；
- `screening_group_industry_shard_validation.status == passed`；
- candidate、完整 screening view、industry shards 股票全集一致；
- candidate code 唯一；
- `research/trend_handoff.json` 可解析；
- `result_kind == a_share_trend_handoff`；
- handoff `trade_date == runtime.trade_date`；
- 每条 signal 至少包含 `trend_name / trend_state / industry_codes / industry_names`；
- 每个已解析 industry code 必须能在 `screening_group_index_file` 中解析。

`industry_state` 与 `buyability` 不再是买点榜行业入口 Hard Gate，也不得用于重新选择或重排趋势行业。

若 handoff 合法但 `signals` 为空，本轮可直接 COMPLETE，并标记 `NO_ACTIVE_TREND`，不强行寻找公司。

若某个已解析行业在 runtime 中没有候选，记录 `NO_RUNTIME_CANDIDATE`；这不是整轮 FAILED。

---

## 3. Trend Handoff / Routing

趋势榜是唯一行业发现器。买点榜不得再次执行“景气 + 资金 + 可买性”排序，也不得执行动态 3–5 行业扩展。

执行：

1. 保留 handoff 中 signals 原顺序；
2. 对全部已解析 `industry_codes` 做有序去重，形成 `routed_industry_codes`；
3. 读取这些行业的完整 runtime shards；
4. 公司研究全集 = routed shards 中全部 runtime candidates 的精确并集；
5. 保存每家公司来自哪些 `trend_name / trend_state`，供后续 Expectation 使用。

行业代码只承担路由功能，不构成买卖判断。

---

## 4. Fresh Transaction / Coverage

每次触发生成新 `run_id`，从新的公司全集开始。不得 resume，不得复用上一轮公司结论。

不再要求旧版 Stage A → Q1 → Q2 → Q2-lite → Deep Research 五层正式漏斗；这些旧指标仍可作为事实输入，但不得成为与前瞻预期脱节的机械硬门。

全流程不得 Top N、不得行业配额、不得因为已有 READY 提前停止。

---

## 5. Transmission｜趋势是否真正传导到公司

对 routed company universe 全覆盖判断：

- `SUPPORTED`
- `NOT_SUPPORTED`
- `UNCERTAIN`

核心问题：

> 趋势榜发现的变化，是否有客观路径进入这家公司未来 1–2 个季度的收入、利润或现金流？

优先证据：

- 已签/在手订单及交付窗口；
- 产品价格或价差变化；
- 销量/出货变化；
- 新产能投产与爬坡；
- 客户定点/认证；
- 库存周期变化；
- 市占率或产品结构变化。

“属于这个行业”本身不足以证明传导。PE、ROE、当期利润、现金流等可用于解释风险，但任何单一历史指标都不得自动否决有明确前瞻传导证据的公司。

`NOT_SUPPORTED` → `DROP`。

`UNCERTAIN` 允许一次定向补查；仍存在关键缺口则保留 `UNCERTAIN`。

---

## 6. Expectation｜市场已经交易到哪一步

对 Transmission `SUPPORTED` 的公司重建：

```text
催化/订单/价格变化何时出现
→ 股价何时开始反应
→ 财务数字何时开始兑现
→ 当前还有多少增量预期尚未体现
```

预期阶段只允许：

- `EARLY`：催化已出现，财报和股价尚未充分反映；
- `CONFIRMING`：订单/价格/销量开始兑现，市场开始确认，仍有可验证的后续增量；
- `PRICED_IN`：主要催化已带来显著重估且财务已大量兑现，新增惊喜有限；
- `EXHAUSTED`：利好仍在公布但股价不再确认或边际盈利驱动转弱；
- `UNCERTAIN`：时间链或定价证据不足/冲突。

不得仅凭一天涨跌或单个技术位置判断预期阶段。

`PRICED_IN / EXHAUSTED` 不自动 DROP；若基本面仍成立但缺乏新的预期周期，通常进入 WAIT，而不是因为股价从高点跌很多就重新 READY。

---

## 7. Risk–Reward｜最后才判断买点

只有 Transmission 有支持且 Expectation 足够明确的公司进入统一风险收益评估：

```text
未来 1–2 季度可验证驱动
→ 正常化/前瞻盈利区间
→ 中枢 × 可辩护的保守估值
→ conservative fair value
→ low-risk buy range / downside anchor
→ conservative upside
```

原则：

1. 强周期公司使用正常化盈利，不得峰值简单年化；
2. 当前历史 PE 只是背景，不替代前瞻盈利；
3. 原则上 `conservative_upside >= 15%`；
4. 当前价原则上应接近低风险安全区，或存在同等可量化的下行保护；
5. 必须明确最可能推翻逻辑的事实与失效条件。

最终状态：

- `READY`：Transmission 支持 + Expectation 为 EARLY/CONFIRMING（或有明确新的预期重置）+ 风险收益合格；
- `WAIT`：逻辑成立，但价格、预期阶段或安全边际尚不合适；
- `UNCERTAIN`：关键证据缺口/冲突；
- `DROP`：传导/核心逻辑被实质反证，或风险收益结构性不成立。

---

## 8. Coverage / 正式发布

只有同时满足：

```text
runtime_hard_gate = PASSED
trend_handoff_gate = PASSED
routing_coverage = COMPLETE
transmission_coverage = COMPLETE
expectation_coverage = COMPLETE
risk_reward_coverage = COMPLETE
publication_ready = true
```

才允许覆盖：

```text
research/latest_formal_result.json
```

FAILED / INCOMPLETE / UNVERIFIED 绝不能覆盖上一份 COMPLETE。

正式结果至少保存：

- `schema_version`
- `result_kind = a_share_low_risk_formal_result`
- `status = COMPLETE`
- `trade_date / run_id / published_at`
- `source_runtime_commit_sha`
- `trend_handoff`
- `routed_industries`
- `ready / wait / uncertain / drop`
- `funnel`

为兼容早间版，可同时写别名：

- `confirmed = ready`
- `waiting_for_entry = wait`
- `research_uncertain = uncertain`
- `excluded = drop`

每只 READY / WAIT 至少保存：code、name、trend_name、trend_state、industry、expectation_stage、current_price、reasonable_price_range、low_risk_buy_range、transmission_evidence、pricing_evidence、invalidation、primary_profit_driver、dominant_risk_factor。

写入后必须立即回读校验。

---

## 9. 正式输出

### A.【趋势路由】

```text
趋势主题｜趋势状态｜三级行业｜行业代码
```

### B.【A股低风险买点榜】

```text
股票｜趋势主题｜三级行业｜预期阶段｜状态｜当前价｜合理价值区｜低风险区｜传导/催化证据｜市场已定价证据｜失效条件｜核心风险
```

### C.【筛选漏斗】

至少给出：trend signals、routed industries、routed candidates、Transmission 各状态数、Expectation 各阶段数、READY / WAIT / UNCERTAIN / DROP 数。

---

## 10. 07:00 早间版

早间版只读取上一份 COMPLETE `latest_formal_result.json`，围绕 READY / WAIT 做隔夜事实核验，不新增公司、不重新做 Expectation、不主动升级状态。

若正式结果缺失、非 COMPLETE 或 trade_date 与当前最新正式 runtime 不一致：

```text
MORNING_HANDOFF_UNAVAILABLE
```

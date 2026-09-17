# A股低风险买点榜｜运行时执行协议

本文件是唯一正式执行契约。趋势榜负责发现趋势，买点榜通过趋势 handoff 路由到公司，并依次完成 Transmission → Expectation → Risk–Reward。

## 1. 正式输入

### 1.1 19:00 / 手动正式版

读取当前 `main`：

- `skill/RUNTIME_READ_PROTOCOL.md`
- `skill/SKILL.md`
- `research/trend_handoff.json`
- `research/theme_alias_map.json`
- `data/runtime/meta.json`
- `meta.screening_group_index_file`
- handoff 中所有已解析且当前 screening runtime 中存在的 `industry_codes` 对应的 `screening_groups_by_industry/<industry_code>.json`

每次正式触发都是新的独立事务，生成新的 `run_id`，从当次 routed company universe 开始。

### 1.2 07:00 早间版

读取：

- `skill/RUNTIME_READ_PROTOCOL.md`
- `research/latest_formal_result.json`
- 当前最新有效正式收盘 `data/runtime/meta.json`

早间版只做隔夜增量复核。

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
- 每条 signal 至少包含 `trend_name / trend_state / market_state / industry_codes / industry_names`。

若 `signals` 为空，本轮可直接 COMPLETE，并标记 `NO_ACTIVE_TREND`。

行业映射与当日候选可用性是两个独立状态：

- 趋势主题优先沿用 handoff 已解析的申万三级行业；
- 若某个 signal `mapping_status == unresolved`，允许使用 `research/theme_alias_map.json` 中与该主题完全匹配的显式 alias 路由；
- alias 命中后即视为行业映射已解析，不要求该行业必须出现在当前 `screening_group_index_file`；
- 若 alias 命中得到的行业当前没有 screening runtime 候选，记录 `NO_RUNTIME_CANDIDATE`，不得重新降级为 `ROUTING_UNRESOLVED`；
- 只有 handoff 与 alias map 都无法解析主题时，才记录 `ROUTING_UNRESOLVED`，不得猜测代码。

---

## 3. Trend Handoff / Routing

1. 保留 handoff 中 signals 原顺序；
2. 先使用 handoff 自带 `industry_codes / industry_names`；
3. 对 unresolved signal，仅允许使用 `research/theme_alias_map.json` 中完全匹配的人工维护 alias；
4. alias 只负责把市场主题转换成已确认的申万三级行业代码/名称，不参与趋势评分、升级、降级或买卖判断；
5. 对所有已解析行业代码有序去重：若代码存在于当前 `screening_group_index_file`，读取对应完整 industry shard；若不存在，记录该行业 `NO_RUNTIME_CANDIDATE`，不尝试读取不存在的 shard；
6. 公司研究全集 = 所有当前 runtime 中可用的 routed industry candidates 的精确并集；
7. 保存每家公司对应的 `trend_name / trend_state / market_state`；
8. `market_state` 只作为市场生命周期上下文，不修改趋势榜结论。

行业代码和 theme alias 只承担路由功能，不构成买卖判断。

---

## 4. Coverage

全流程不得 Top N、不得行业配额、不得因为已有 READY 提前停止。

必须记录并闭合：

- `routing_coverage`
- `transmission_coverage`
- `expectation_coverage`
- `risk_reward_coverage`

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

“属于这个行业”本身不足以证明传导。历史财务与估值用于解释风险和质量，不替代前瞻传导判断。

`NOT_SUPPORTED` → `DROP`。

`UNCERTAIN` 允许一次定向补查；仍有关键缺口则保留 `UNCERTAIN`。

Transmission coverage 完成条件：

```text
transmission_processed_codes == routed_company_codes
```

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

- `EARLY`
- `CONFIRMING`
- `PRICED_IN`
- `EXHAUSTED`
- `UNCERTAIN`

定义：

- `EARLY`：催化已出现，财报和股价尚未充分反映；
- `CONFIRMING`：基本面开始兑现，市场开始确认，未来 1–2 季度仍有可验证增量；
- `PRICED_IN`：主要催化已推动显著重估且财务已大量兑现，新增惊喜有限；
- `EXHAUSTED`：利好仍在公布但股价不再确认，或核心驱动边际转弱；
- `UNCERTAIN`：时间链或定价证据不足/冲突。

不得仅凭一天涨跌或单个技术位置判断预期阶段。

趋势 handoff 的 `market_state` 是重要上下文，但公司 expectation 必须由自身事件—价格—财务时间链验证。

若 Expectation = `PRICED_IN / EXHAUSTED` 且没有新的独立预期重置：

```text
status = WAIT
wait_reason = WAIT_EXPECTATION
```

Expectation coverage 必须覆盖全部 Transmission `SUPPORTED` 公司。

---

## 7. Risk–Reward｜最后判断买点

完整 Risk–Reward universe：

```text
Transmission = SUPPORTED
AND
(
  Expectation in {EARLY, CONFIRMING}
  OR 新的独立预期重置成立
)
```

统一执行：

```text
未来 1–2 季度可验证驱动
→ 正常化/前瞻盈利区间
→ 中枢 × 可辩护保守估值
→ conservative fair value
→ low-risk buy range / downside anchor
→ conservative upside
```

原则：

1. 强周期公司使用正常化盈利，不得峰值简单年化；
2. 当前历史 PE 只是背景，不替代前瞻盈利；
3. 原则上 `conservative_upside >= 15%`；
4. 当前价原则上应接近低风险安全区，或存在同等可量化下行保护；
5. 必须明确最可能推翻逻辑的事实与失效条件。

最终状态：

- `READY`
- `WAIT`
- `UNCERTAIN`
- `DROP`

WAIT 原因标签：`WAIT_EXPECTATION / WAIT_PRICE / WAIT_MARGIN / WAIT_CATALYST`。

Risk–Reward coverage 完成条件：

```text
所有 EARLY / CONFIRMING / 新预期重置公司完成风险收益判断
+
所有 PRICED_IN / EXHAUSTED 无重置公司记录 WAIT_EXPECTATION
```

---

## 8. 正式发布

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

FAILED / INCOMPLETE / UNVERIFIED 不得覆盖上一份 COMPLETE。

正式结果至少保存：

- `schema_version`
- `result_kind = a_share_low_risk_formal_result`
- `status = COMPLETE`
- `trade_date / run_id / published_at`
- `source_runtime_commit_sha`
- `trend_handoff`
- `routing_gaps`
- `routed_industries`
- `ready / wait / uncertain / drop`
- `funnel`

为兼容早间版，可同时写别名：

- `confirmed = ready`
- `waiting_for_entry = wait`
- `research_uncertain = uncertain`
- `excluded = drop`

每只 READY 以及因价格/安全边际等待的 WAIT 至少保存：code、name、trend_name、trend_state、market_state、industry、expectation_stage、current_price、reasonable_price_range、low_risk_buy_range、transmission_evidence、pricing_evidence、invalidation、primary_profit_driver、dominant_risk_factor。

`WAIT_EXPECTATION` 可将 reasonable/low-risk range 写为 `N/A`，但必须保存 expectation_stage、pricing_evidence 与重新进入估值研究的触发条件。

写入后必须立即回读校验。

---

## 9. 正式输出

### A.【趋势路由】

```text
趋势主题｜产业状态｜市场状态｜三级行业｜行业代码｜映射状态
```

### B.【A股低风险买点榜】

```text
股票｜趋势主题｜三级行业｜预期阶段｜状态｜WAIT原因｜当前价｜合理价值区｜低风险区｜传导/催化证据｜市场已定价证据｜失效条件｜核心风险
```

### C.【筛选漏斗】

至少给出：

- trend signals 总数 / resolved / unresolved；
- routed industries 数量；
- routed runtime candidate 数；
- Transmission SUPPORTED / UNCERTAIN / NOT_SUPPORTED；
- Expectation EARLY / CONFIRMING / PRICED_IN / EXHAUSTED / UNCERTAIN；
- READY / WAIT / UNCERTAIN / DROP。

---

## 10. 07:00 早间版

读取上一份 `research/latest_formal_result.json`，要求 `status == COMPLETE` 且 `trade_date == 当前最新有效正式收盘 runtime.trade_date`。

若无有效交接：

```text
MORNING_HANDOFF_UNAVAILABLE
```

若有效，只围绕 READY / WAIT 检查隔夜商品、海外同行、重大公告、政策或突发是否改变原 Transmission / Expectation / Risk–Reward。

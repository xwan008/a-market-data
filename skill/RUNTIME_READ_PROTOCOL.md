# A股低风险买点榜｜运行时与发布协议

## 1. 职责边界

本文件只负责：
- runtime / handoff 有效性校验；
- 正式结果发布 Gate；
- 结果回读校验；
- 07:00 早间增量版。

**本文件不定义 Universe、不定义公司事实读取路径、不定义 working set 构造方式。**

正式主流程唯一以：
`skill/LOW_RISK_CANONICAL_FLOW.md`
为准。

若本文件与 canonical flow 冲突，以 canonical flow 为准。

---

## 2. 19:00 / 手动正式版输入

必须读取当前 main：

- `skill/LOW_RISK_CANONICAL_FLOW.md`
- `research/trend_handoff.json`
- `data/runtime/meta.json`
- canonical flow 要求的阶段规则文件

Universe、shard 读取和 run-local working set 构造严格由 canonical flow 负责。

本任务**不得**把以下文件作为 Universe 或事实入口：

- `data/runtime/screening_group_index.json`
- `data/runtime/screening_groups_by_industry/*.json`
- 任何 candidate/compact cache

这些文件可服务仓库其他流程，但不属于低风险买点榜正式数据链。

---

## 3. Runtime / Handoff Hard Gate

正式版至少确认：

- `runtime_validation.status == passed`；
- `research/trend_handoff.json` 可解析；
- `result_kind == a_share_trend_handoff`；
- handoff `trade_date == runtime.trade_date`；
- 每条 signal 至少包含：
  - `trend_name`
  - `trend_state`
  - `market_state`
  - `industry_codes`
  - `industry_names`
- 已解析 signal 的行业代码能够交给 canonical flow 路由。

若 `signals` 为空，本轮可直接 COMPLETE，并标记：
`NO_ACTIVE_TREND`。

不得因为 routed 行业不在 screening runtime/candidate cache 中而判定：
`NO_RUNTIME_CANDIDATE`。

---

## 4. Working Set Freeze Gate

正式版进入公司级分析前必须满足：

```text
working_set_count == routed_industry_count
working_set_company_count == universe_company_count
post_freeze_shard_read_count == 0
```

其中：
- Universe 唯一来自 `data/research/company_industry_index.json`；
- 公司完整事实由 canonical flow 在 Freeze 前从去重 shard 一次性提取；
- Freeze 后不得再读取 company_industry_index 或任何个股 shard；
- 后续硬过滤、预筛、Transmission、Expectation、估值与价格区间全部消费 frozen working set。

若 Freeze Gate 不成立，正式版不得覆盖上一份 COMPLETE。

---

## 5. Coverage / Publication Gate

只有同时满足：

```text
runtime_hard_gate = PASSED
trend_handoff_gate = PASSED
working_set_gate = PASSED
routing_coverage = COMPLETE
pre_screen_coverage = COMPLETE
transmission_coverage = COMPLETE
expectation_coverage = COMPLETE
risk_reward_coverage = COMPLETE
price_range_coverage = COMPLETE
publication_ready = true
```

才允许覆盖：

`research/latest_formal_result.json`

FAILED / INCOMPLETE / UNVERIFIED 不得覆盖上一份 COMPLETE。

正式结果至少保存：

- `schema_version`
- `result_kind = a_share_low_risk_formal_result`
- `status = COMPLETE`
- `trade_date / run_id / published_at`
- runtime / handoff provenance
- `trend_handoff`
- `routing_gaps`
- `routed_industries`
- `hard_filtered_out`
- `pre_screen_selected`
- `pre_screened_out`
- `ready / wait / uncertain / drop`
- `coverage`
- `data_access_audit`
- `execution_audit`
- `funnel`

推荐 data access 审计字段：

```json
{
  "routed_industry_count": 0,
  "universe_company_count": 0,
  "working_set_count": 0,
  "working_set_company_count": 0,
  "unique_shard_read_count": 0,
  "post_freeze_shard_read_count": 0
}
```

不再使用 `compact_cache_hit_count`、`new_shard_fallback_company_count` 等旧主链审计字段。

写入后必须立即回读校验 JSON、status、trade_date、run_id、coverage 与 data_access_audit。

---

## 6. READY / WAIT 价格完整性

READY / WAIT 的价格字段完整性由：
`PRICE_RANGE_OUTPUT_OVERRIDE.md`
负责。

本协议不允许任何规则绕过价格区间 Gate。

正式榜中的 WAIT 不得因为旧协议而允许 `N/A` 区间；无法形成可辩护区间时按价格规则进入 UNCERTAIN。

---

## 7. 07:00 早间增量版

读取：

- 上一份 `research/latest_formal_result.json`
- 当前最新有效正式收盘 `data/runtime/meta.json`
- 必要的隔夜公开信息

要求上一份正式结果：
- `status == COMPLETE`
- `trade_date == 当前最新有效正式收盘 trade_date`

若无有效交接：

`MORNING_HANDOFF_UNAVAILABLE`

早间版只围绕上一正式版 READY / WAIT 检查隔夜新增信息是否改变：

- Transmission
- Expectation
- Risk–Reward
- 已有价格区间的有效性

默认复用上一正式版已验证研究，不从零重建正式流程。

如重大新信息使价格区间失效，明确标记下一正式版需要重算，不得继续沿用失效区间。

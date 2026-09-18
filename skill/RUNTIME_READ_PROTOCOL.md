# A股低风险买点榜｜运行时与发布协议

## 1. 职责边界

本文件只负责：
- materialized view / handoff 有效性校验；
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
- `data/low_risk/index.json`
- canonical flow 要求的阶段规则文件

Universe 权威来源、预物化行业事实读取和 run-local working set 构造严格由 canonical flow 负责。正式榜运行时使用 `data/low_risk/index.json`，再按 index 指向读取 routed 行业的 `manifest.json + part-xxx.json`；不得读取 legacy 单行业大文件，也不得重新现场解析 company_industry_index 或 shards。

19:00 正式版与手动正式版均为 Fresh Run：不得读取上一份 `research/latest_formal_result.json` 作为本轮计算输入，不得复用上一轮 working set、pre-screen、Transmission、Expectation、valuation 或 Price Range 结论来跳过阶段。上一份 COMPLETE 只允许在本轮完成后用于差异对比。07:00 早间增量版除外。

正式版 / 手动版必须执行 canonical flow 定义的 **Materialized Runtime View Protocol**：先读取 `data/low_risk/index.json`，校验 trade_date、validation 与 `materialized_layout == "chunked_manifest_v1"`。对 routed 行业，index 中存在者读取对应 `manifest_file`，再按 manifest.parts 顺序完整读取全部 part；在已通过全量分区校验的 index 中不存在者标记 `NO_UNIVERSE_MEMBER`。manifest/parts 由 GitHub Actions 从 company_industry_index + shards 确定性生成并校验；正式榜不得回退读取大 JSON 或 legacy 单行业文件。

旧 `data/snapshot.json`、`data/runtime/*`、screening group、candidate/compact cache 均属于已停用 Legacy Runtime artifacts。它们即使仍作为历史文件保留，也不得参与任何正式版、手动版或早间版计算、Gate、freshness 判断或 fallback。

---

## 3. Materialized View / Handoff Hard Gate

正式版至少确认：

- `data/low_risk/index.json` 可解析；
- `runtime_format == "low_risk_industry_working_set_index"`；
- `validation.status == passed`；
- `materialized_layout == chunked_manifest_v1`；
- `validation.chunk_manifest_complete == true`；
- `validation.chunk_company_coverage_exact == true`；
- `validation.chunk_size_within_limit == true`；
- `research/trend_handoff.json` 可解析；
- `result_kind == a_share_trend_handoff`；
- handoff `trade_date == data/low_risk/index.json.trade_date`；
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
working_set_count == routed_industry_with_universe_count
working_set_company_count == universe_company_count
post_freeze_shard_read_count == 0
```

其中：
- Universe 权威来源仍是 `data/research/company_industry_index.json`，但运行时通过 GitHub Actions 已验证的 `data/low_risk/*` 物化视图消费；
- 公司完整事实权威来源仍是 `data/shards/*.json`，但运行时不直接读取 shards；
- Freeze 前每个 routed 行业 manifest 最多读取一次；manifest 声明的每个 part 必须从第1行连续分页读取到 EOF。一个 part 可有多个物理 segment fetch，但完整拼接、JSON 解析和字段校验全部通过后才算 1 个逻辑 part read；
- Freeze 前必须证明 manifest company_count、parts company_count、company codes 与 index 完整一致且无重复；
- Freeze 后不得再读取任何 manifest、part、legacy materialized industry file、company_industry_index 或 shard；
- 后续硬过滤、预筛、Transmission、Expectation、估值与价格区间全部消费 frozen working set。

运行时 `unique_shard_read_count == 0`，因为 shard ETL 已在 GitHub Actions 数据生产层完成；应记录 `materialized_manifest_read_count`、`materialized_part_read_count`、`materialized_part_segment_fetch_count`、`materialized_industry_complete_count`、`legacy_industry_file_read_count` 与 `post_freeze_materialized_read_count`。

若 Freeze Gate 不成立，正式版不得覆盖上一份 COMPLETE。

---

## 5. Coverage / Publication Gate

只有同时满足：

```text
materialized_view_gate = PASSED
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
- materialized view / handoff provenance
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
  "routed_industry_with_universe_count": 0,
  "no_universe_industry_count": 0,
  "universe_company_count": 0,
  "working_set_count": 0,
  "working_set_company_count": 0,
  "materialized_index_read_count": 1,
  "materialized_industry_read_count": 0,
  "unique_shard_read_count": 0,
  "post_freeze_shard_read_count": 0,
  "post_freeze_materialized_read_count": 0
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
- 当前最新有效正式收盘 `data/low_risk/index.json`
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

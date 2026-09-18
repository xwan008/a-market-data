# A股低风险买点榜｜唯一主流程

本文件定义“A股低风险买点榜”的唯一主流程。若其他协议/Override 对执行顺序、Universe 来源、数据读取方式存在冲突，以本文件为准；其他文件只负责各阶段具体判定算法。

## 1. 唯一主流程

```text
Trend Handoff
→ 解析本轮三级行业
→ 读取 data/low_risk/index.json（GitHub Actions 已从 company_industry_index + shards 确定性物化）
→ 只读取 routed 三级行业对应的 data/low_risk/by_industry/<industry_code>.json
→ 将这些行业事实文件复制/映射为本轮 run-local working set
→ Freeze；以下阶段不再读取任何 company_industry_index / shard / low_risk 行业文件
→ 公司级硬过滤
→ 行业内轻量预筛（Top5 / 并列第6）
→ Transmission
→ Expectation
→ 行业自适应估值 + 价格结构
→ reasonable_price_range / low_risk_buy_range
→ READY / WAIT / UNCERTAIN / DROP
→ 正式榜单
```

不得建立第二套并行主流程。

### 正式版 / 手动版 Fresh Run 纪律

19:00 正式版与任何手动正式版，每次执行都必须从 Trend Handoff 开始重新完整执行本文件主流程。上一轮 `latest_formal_result.json`、上一轮 working set、上一轮 pre-screen、Transmission、Expectation、valuation / Price Range 结论只能用于任务结束后的对比，不得作为本轮计算输入，也不得用于跳过任何阶段。

07:00 早间版是唯一允许基于上一份 COMPLETE 做增量复核的例外，具体规则由 `RUNTIME_READ_PROTOCOL.md` 定义。

## 2. 第一步：Trend Handoff 只决定行业

读取 `research/trend_handoff.json`。

只负责：
- 当期新仓优先趋势；
- 对应申万三级行业代码；
- 趋势/市场状态透传。

不负责个股准入、个股估值或买入区间。

## 3. 第二步：从预物化行业事实生成本轮 Working Set

### 3.1 数据权威与运行时视图

低风险榜的数据权威**没有改变**：

- Universe 权威来源：`data/research/company_industry_index.json`；
- 公司事实权威来源：`data/shards/<前5位>.json`。

但正式版 / 手动版运行时**不得再让模型现场解析上述大 JSON**。GitHub Actions 在每次有效正式收盘数据更新后运行：

`scripts/build_low_risk_working_sets.py`

由 Python 确定性执行：

```text
company_industry_index.json
+ data/shards/*.json
→ industry partition
→ exact join
→ standard fact projection
→ validation
→ data/low_risk/index.json
→ data/low_risk/by_industry/<industry_code>.json
```

因此 `data/low_risk/*` 是上述权威数据的**物化运行时视图**，不是第二套 Universe、candidate cache、screening 结果或选股规则。

GitHub 构建必须保证：
- mapped company coverage exact；
- industry partition exact；
- shard trade_date consistent；
- index / shard industry mapping consistent；
- 任一缺失或不一致则 Actions 失败，不得提交半成品。

### 3.2 Runtime Materialized View Gate

正式版 / 手动版从 Trend Handoff 得到 routed 三级行业后，先读取：

`data/low_risk/index.json`

必须满足：
- `runtime_format == "low_risk_industry_working_set_index"`；
- `validation.status == "passed"`；
- `trade_date == 本轮最新有效正式收盘 trade_date`；
- 对每个 routed 三级行业：若存在于 `industries`，则读取对应 materialized file；若在一个 `validation.status == passed` 且全量分区精确的 index 中不存在，则标记 `NO_UNIVERSE_MEMBER`，不读取文件，也不视为数据故障；
- 对应 `file` 指向 `data/low_risk/by_industry/<industry_code>.json`。

index 本身无效、trade_date 不匹配，或 index 明明列出某行业但对应 materialized file 缺失/校验失败时，才阻断 Working Set Gate；不得回退为模型现场读取完整 `company_industry_index.json` 或 shards 来“补跑”。

### 3.3 每行业一个事实文件

对每个 routed 三级行业只读取一次：

`data/low_risk/by_industry/<industry_code>.json`

每个文件必须至少包含：
- `runtime_format == "low_risk_industry_working_set"`；
- trade_date；
- industry_code / industry_name；
- company_count；
- universe_company_codes；
- source provenance；
- companies 全量标准事实。

公司事实至少包括：
- code / name / industry_code / industry_name；
- current price / market cap；
- PE TTM / dynamic PE / PB / ROE；
- revenue_yoy / net_profit_yoy / deduct_basic_eps_yoy；
- operating_cashflow_per_share / gross_margin / EPS；
- MA20 / MA60；
- high_60d / low_60d / position_pct；
- support zones；
- resistance zones；
- dense / volume-profile price zones；
- trend_state / break_state / invalidation；
- 其他硬过滤、预筛和估值需要的已物化 runtime facts。

读取后立即映射为本轮 run-local working set：

```text
working_set[S370603] = data/low_risk/by_industry/S370603.json
working_set[S630602] = data/low_risk/by_industry/S630602.json
...
```

这些 run-local working sets 只存在于本轮执行上下文；仓库里的 `data/low_risk/by_industry/*.json` 是数据生产层的预物化事实文件，不包含本轮 PRE_SCREEN / Transmission / Expectation / valuation / Price Range 结论。

### 3.4 Freeze Gate

Freeze 前必须校验每个 routed 行业：

```text
industry_file.trade_date == data/low_risk/index.json.trade_date
industry_file.company_count == len(industry_file.companies)
industry_file.company_count == len(industry_file.universe_company_codes)
set(companies[*].code) == set(universe_company_codes)
index.industries[industry_code].company_count == industry_file.company_count
```

并校验：

```text
working_set_count == routed_industry_with_universe_count
working_set_company_count == sum(routed industries with universe 的 company_count)
```

通过后 Freeze。

**从此之后，本轮硬过滤、预筛、Transmission、Expectation、估值和价格区间只消费 frozen working set。不得再读取 `company_industry_index.json`、任何 `data/shards/*.json`、或再次读取 `data/low_risk/by_industry/*.json`。**

正式版 / 手动版的 Fresh Run 仍然成立：每轮都必须重新从 Trend Handoff 路由、重新读取当期 routed 行业事实、重新执行 Hard Filter → Pre-screen → Transmission → Expectation → valuation / Price Range。预物化只替代底层 deterministic ETL，不得复用上一轮研究结论。

## 4. Stage A：公司级硬过滤

只对 frozen working set 中的公司执行公司级硬条件：
- ST；
- 无效/非正价格；
- 关键数据严重缺失；
- revenue_yoy < -20% 且 net_profit_yoy < -50%；
- 其他正式协议公司级硬条件。

行业景气字段不得作为个股准入 Gate。

## 5. Stage B：行业内轻量预筛

仅对 hard-eligible 公司，使用 working set 已包含的：
- 收入增长；
- 核心利润增长；
- 现金流/一次性收益质量；
- 估值；
- 60日位置。

每个三级行业原则上 Top5；第6名与第5名满足既定 tie 规则时可一起进入，最多6家。

未进入深研：`PRE_SCREENED_OUT`。

## 6. Stage C：Transmission

只对 pre-screen selected 公司研究未来1–2季度行业趋势是否能传导到公司盈利。

Web/公告/IR 只补 working set 不可能提供的前瞻证据，例如订单、产能、交付、客户、产品结构、价格变化。

## 7. Stage D：Expectation

只对 Transmission=SUPPORTED 公司判断：EARLY / CONFIRMING / PRICED_IN / EXHAUSTED / UNCERTAIN。

## 8. Stage E：行业自适应估值与买点

只使用 frozen working set 的估值、财务与价格结构事实，再结合前两阶段必要的前瞻结论：

```text
行业估值原型
+ 同行业 hard-eligible peer statistics
+ 公司增长/ROE/现金流/盈利质量修正
→ fundamental_anchor_price

fundamental_anchor_price
+ MA60 / support / volume-zone
→ reasonable_price_range

reasonable_price_range
+ 行业与60日波动安全边际
→ low_risk_buy_range
```

技术结构只负责择时，不得抬高基本面估值上限。

“没有完整 DCF”本身不得作为 UNCERTAIN 理由。

## 9. I/O 规则

一轮正式执行应近似：

```text
1次 trend_handoff
1次 data/low_risk/index.json
N次 routed industry materialized files（N == routed_industry_with_universe_count，每个有 Universe 的行业最多一次；NO_UNIVERSE_MEMBER 不读文件）
working set freeze
后续 0 次 materialized industry file 读取
全程 0 次 company_industry_index 大文件读取
全程 0 次 data/shards/*.json 读取
必要的行业批次 Web/公告研究
```

禁止：
- 正式榜运行时重新现场解析 `company_industry_index.json` 或 shards；
- 在硬过滤/预筛/估值阶段重新读取行业事实文件；
- 使用 `screening_groups_by_industry`、candidate/compact cache 作为本任务正式主流程的数据层；
- 为物化视图已提供的 PE/PB/MA60/support/volume-zone 再上 Web；
- 将上一轮 working set 或阶段结论作为本轮输入。

旧 `snapshot / runtime / screening_groups / industry_state` artifacts 可暂时作为历史数据保留，但已退出活动生产链；任何正式低风险榜流程不得读取、依赖或回退到这些 Legacy Runtime artifacts。

## 10. 执行审计

正式结果建议保存：

```json
"data_access_audit": {
  "routed_industry_count": 0,
  "routed_industry_with_universe_count": 0,
  "no_universe_industry_count": 0,
  "universe_company_count": 0,
  "working_set_company_count": 0,
  "working_set_count": 0,
  "materialized_index_read_count": 1,
  "materialized_industry_read_count": 0,
  "unique_shard_read_count": 0,
  "post_freeze_shard_read_count": 0,
  "post_freeze_materialized_read_count": 0
}
```

其中：
- `universe_company_count` = 本轮 routed 行业物化事实文件的 company_count 总和；
- `materialized_industry_read_count == routed_industry_with_universe_count`；
- 正式榜运行时不直接读取 shards，因此 `unique_shard_read_count == 0`；
- `post_freeze_shard_read_count == 0`；
- `post_freeze_materialized_read_count == 0`。

发布前要求：
- `working_set_company_count == universe_company_count`；
- `working_set_count == routed_industry_with_universe_count`；
- `materialized_industry_read_count == routed_industry_with_universe_count`；
- 两类 post-freeze read count 都为 0。

否则视为数据访问流程不完整，不得把执行路径描述为 canonical complete。

## 11. 一句话版本

> GitHub Actions 先把 company_industry_index + shards 确定性物化成按三级行业拆分的小事实文件；低风险榜运行时只按 Trend Handoff 读取对应行业文件并 Freeze，之后重新完成预筛、研究、估值与买点，不再让 automation 现场处理大 JSON。

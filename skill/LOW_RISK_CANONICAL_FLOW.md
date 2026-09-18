# A股低风险买点榜｜唯一主流程

本文件定义“A股低风险买点榜”的唯一主流程。若其他协议/Override 对执行顺序、Universe 来源、数据读取方式存在冲突，以本文件为准；其他文件只负责各阶段具体判定算法。

## 1. 唯一主流程

```text
Trend Handoff
→ 解析本轮三级行业
→ 读取 data/low_risk/index.json
→ 对每个 routed 行业读取 manifest.json
→ 按 manifest.parts 顺序读取全部 part-xxx.json，并在本轮上下文中拼接完整行业事实
→ 校验 manifest / parts / index 覆盖完全一致
→ 映射为本轮 run-local working set
→ Freeze；以下阶段不再读取任何 company_industry_index / shard / low_risk manifest / part / legacy 单文件
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

低风险榜的数据权威没有改变：
- Universe 权威来源：`data/research/company_industry_index.json`；
- 公司事实权威来源：`data/shards/<前5位>.json`。

正式版 / 手动版运行时不得现场解析上述大 JSON。GitHub Actions 每次有效正式收盘后运行 `scripts/build_low_risk_working_sets.py`，确定性执行：

```text
company_industry_index.json + data/shards/*.json
→ industry partition / exact join / standard fact projection / validation
→ data/low_risk/index.json
→ data/low_risk/by_industry/<industry_code>/manifest.json
→ data/low_risk/by_industry/<industry_code>/part-001.json ...
```

迁移期暂时继续生成旧 `data/low_risk/by_industry/<industry_code>.json`，但新正式主流程禁止读取该 legacy 单文件。

chunk 生产约束：
- 每 part 默认最多 5 家公司；
- 每 part 紧凑 JSON 默认不得超过 96 KiB；
- 若达到字节上限，允许少于 5 家；
- 单家公司本身超过上限则构建失败；
- manifest 必须列出全部 part、各 part 的 company codes、company_count 与 byte_size。

GitHub 构建必须保证 mapped company coverage、industry partition、trade_date、industry mapping、chunk manifest、chunk company coverage 与 chunk size 全部校验通过；否则不得提交半成品。

### 3.2 Runtime Materialized View Gate

先读取 `data/low_risk/index.json`，必须满足：
- `runtime_format == "low_risk_industry_working_set_index"`；
- `validation.status == "passed"`；
- `materialized_layout == "chunked_manifest_v1"`；
- `validation.chunk_manifest_complete == true`；
- `validation.chunk_company_coverage_exact == true`；
- `validation.chunk_size_within_limit == true`；
- `trade_date == 本轮最新有效正式收盘 trade_date`。

对每个 routed 行业：
- 若存在于 index，必须读取其 `manifest_file`；
- 若在已通过全量覆盖校验的 index 中不存在，标记 `NO_UNIVERSE_MEMBER`；
- `manifest_file` 必须指向 `data/low_risk/by_industry/<industry_code>/manifest.json`；
- index 中 `legacy_file` / `file` 只用于迁移兼容，正式版 / 手动版不得读取。

任何 index / manifest / part 无效时阻断 Working Set Gate；不得回退读取完整 company_industry_index、shards 或 legacy 单文件。

### 3.3 Manifest + Chunk 读取协议

对每个 routed 且有 Universe 的行业：

1. 读取一次 `manifest.json`；
2. 校验：
   - `runtime_format == "low_risk_industry_working_set_manifest"`；
   - `layout_version == 1`；
   - trade_date / industry_code / industry_name 与 index 一致；
   - company_count 与 index 一致；
   - `len(universe_company_codes) == company_count`；
   - `chunking.part_count == len(parts)`；
3. 按 `parts[*].part_number` 升序读取全部 part，每个 part 只读一次，不得抽样或跳读；
4. 每个 part 必须满足：
   - `runtime_format == "low_risk_industry_working_set_chunk"`；
   - trade_date / industry identity 与 manifest 一致；
   - part_number 与 manifest entry 一致；
   - `company_count == len(company_codes) == len(companies)`；
   - `set(companies[*].code) == set(company_codes)`；
   - company_codes 与 manifest 对应 entry 完全一致；
5. 拼接全部 part 的 companies 形成该行业 run-local working set。

公司事实字段仍至少覆盖 code/name、价格/市值、PE/PB/ROE、收入利润现金流、MA20/MA60、60日高低与位置、support/resistance/dense/volume zones、trend_state/break_state/invalidation 等硬过滤、预筛和估值所需事实。

### 3.4 Freeze Gate

Freeze 前每个 routed 行业必须证明：

```text
manifest.trade_date == index.trade_date
manifest.company_count == len(manifest.universe_company_codes)
manifest.company_count == sum(parts[*].company_count)
manifest.parts 中 company_codes 的按序拼接 == manifest.universe_company_codes
实际读取 part company codes 的按序拼接 == manifest.universe_company_codes
set(all part companies[*].code) == set(manifest.universe_company_codes)
不存在重复 code
index.industries[industry_code].company_count == manifest.company_count
实际读取 part 数 == manifest.chunking.part_count == index.industries[industry_code].part_count
working_set_count == routed_industry_with_universe_count
working_set_company_count == sum(routed industries with universe 的 company_count)
```

通过后 Freeze。此后硬过滤、预筛、Transmission、Expectation、估值和价格区间只消费 frozen working set；不得再读取 company_industry_index、shards、manifest、part 或 legacy 单文件。

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
N次 routed industry manifest（N == routed_industry_with_universe_count）
P次 part 文件（P == 所有 routed manifest 声明的 part_count 总和）
working set freeze
后续 0 次 manifest/part/legacy materialized 读取
全程 0 次 company_industry_index 大文件读取
全程 0 次 data/shards/*.json 读取
必要的行业批次 Web/公告研究
```

禁止：
- 正式榜现场解析 company_industry_index 或 shards；
- 读取 legacy `data/low_risk/by_industry/<industry_code>.json`；
- 跳读、抽样或重复读取 manifest 声明的 part；
- Freeze 后再读取 manifest / part；
- 使用 screening_groups、candidate/compact cache 作为正式主流程数据层；
- 为物化视图已有 PE/PB/MA60/support/volume-zone 再上 Web；
- 将上一轮 working set 或阶段结论作为本轮输入。

旧 snapshot/runtime/screening_groups/industry_state 及 legacy 单行业大文件可暂时保留，但已退出活动生产链。

## 10. 执行审计

正式结果保存：

```json
"data_access_audit": {
  "routed_industry_count": 0,
  "routed_industry_with_universe_count": 0,
  "no_universe_industry_count": 0,
  "universe_company_count": 0,
  "working_set_company_count": 0,
  "working_set_count": 0,
  "materialized_index_read_count": 1,
  "materialized_manifest_read_count": 0,
  "materialized_part_read_count": 0,
  "materialized_industry_complete_count": 0,
  "unique_shard_read_count": 0,
  "legacy_industry_file_read_count": 0,
  "post_freeze_shard_read_count": 0,
  "post_freeze_materialized_read_count": 0
}
```

发布前要求：
- `materialized_manifest_read_count == routed_industry_with_universe_count`；
- `materialized_part_read_count == routed manifest 声明的 part_count 总和`；
- `materialized_industry_complete_count == routed_industry_with_universe_count`；
- `legacy_industry_file_read_count == 0`；
- `unique_shard_read_count == 0`；
- `working_set_company_count == universe_company_count`；
- `working_set_count == routed_industry_with_universe_count`；
- 两类 post-freeze read count 都为 0。

否则不得把执行路径描述为 canonical complete。

## 11. 一句话版本

> GitHub Actions 把 company_industry_index + shards 确定性物化成“行业 manifest + 有界小 part”；低风险榜按 Trend Handoff 完整读取 manifest 声明的全部 parts、证明 Universe 无遗漏后 Freeze，再完成预筛、研究、估值与买点，规避单个行业大 JSON 被工具截断的问题。

# A股低风险买点榜｜唯一主流程

本文件定义“A股低风险买点榜”的唯一主流程。若其他协议/Override 对执行顺序、Universe 来源、数据读取方式存在冲突，以本文件为准；其他文件只负责各阶段具体判定算法。

## 1. 唯一主流程

```text
Trend Handoff
→ 解析本轮三级行业
→ company_industry_index 找出每个行业全部策略公司
→ 按所需 shard 前缀去重后分批读取；工具内立即解析并只投影目标公司事实
→ 动态生成“本轮行业工作集”（每个三级行业一个 working set）
→ 冻结 working set；以下阶段不再读取 company_industry_index / shard
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

## 3. 第二步：动态生成本轮行业工作集

### 3.1 Universe

`data/research/company_industry_index.json` 是“某三级行业有哪些策略公司”的唯一权威来源。

读取该文件时采用同源容错：优先使用标准文件读取；若返回空内容、截断或不可解析，不得据此判定 Universe 为空，应立即改用 GitHub REST Contents/Blob 对**同一 main 分支、同一路径、同一文件**重读。只有两种读取方式都失败或都无法解析时，才允许将 Universe 构建判定为失败。该容错只改变读取方式，不改变 Universe 来源。

对每个 resolved 三级行业：
1. 从 company_industry_index 找出全部策略公司；
2. 得到 `universe_company_codes`；
3. 不得使用 screening_group / candidates 是否存在来决定公司是否属于该行业。

### 3.2 Facts

根据 `universe_company_codes` 计算所需 `data/shards/<前5位>.json`，按 shard 前缀去重后采用小批次读取。工具层可分成多个 batch，以避免单轮工具调用上限。

每个 shard 的读取必须在**同一次工具调用内部**完成以下动作后，才把结果返回执行上下文：

1. 读取该 shard；
2. 立即解析 JSON；
3. 根据本轮 `universe_company_codes` 只抽取该 shard 中真正需要的目标公司；
4. 立即投影为 working set 所需的标准公司事实；
5. 只返回这些目标公司的标准化事实，不得把完整 shard 原文返回模型上下文。

“每个唯一 shard 本轮最多读取一次”是指**最多成功物化一次**。只有满足“JSON 可解析 + 本轮目标公司抽取完成 + 标准字段投影完成”才记为成功读取。若标准读取返回空内容、明显截断或 JSON 不可解析，该次只算读取路径失败，不计入成功读取次数；允许对**同一 main、同一路径、同一 shard**改用 GitHub REST Contents/Blob 做一次同源 fallback。fallback 成功后不得再读该 shard；fallback 仍失败才标记该 shard 读取失败并阻断 Working Set Freeze。

所有所需 shard 的目标公司事实收集完成后，再统一构造本轮 working sets。

从 shard 为每家公司提取本轮后续所需的完整事实，至少包括：
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
- 其他硬过滤、预筛和估值需要的已有 runtime facts。

### 3.3 每行业一个 Working Set

对每个 routed 三级行业即时构造一个 run-local working set，例如：

```text
working_set[S370603] = CRO 全部策略公司完整事实
working_set[S630602] = 风电零部件全部策略公司完整事实
working_set[S270108] = 半导体设备全部策略公司完整事实
working_set[S270103] = 半导体材料全部策略公司完整事实
```

概念上等价于本轮临时 JSON 文件：

```text
<run-local>/routed_industries/S370603.json
<run-local>/routed_industries/S630602.json
<run-local>/routed_industries/S270108.json
<run-local>/routed_industries/S270103.json
```

这些是“本轮执行工作文件”，不是仓库长期数据，不要求写回 GitHub。执行环境若不提供临时文件系统，可用等价的内存 JSON 对象；语义必须相同。

### 3.4 Freeze Gate

working set 构建完成后必须校验：

```text
union(working_set[*].company_codes)
== 本轮 routed industries 在 company_industry_index 中的 universe_company_codes
```

校验通过后冻结 working set。

**从此之后，本轮的硬过滤、预筛、Transmission、Expectation、估值、价格区间全部只消费 working set。不得再回头逐股读取 shard，也不得再用 screening_groups_by_industry 补数据。**

若 working set 生成阶段本身缺失关键事实，应在生成阶段一次性解决或标记数据缺失；不得拖到后面阶段反复 I/O。

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
1次 company_industry_index
N个唯一 shard 的目标公司事实物化，可按小批次执行；成功物化后不得重读，全部收集后统一构建 routed working sets
working set freeze
后续 0 次 company_industry_index 读取
后续 0 次 shard 读取
必要的行业批次 Web/公告研究
```

禁止：
- 在硬过滤/预筛/估值阶段重新逐股 fetch shard；
- 使用 `screening_groups_by_industry` 作为本任务正式主流程的数据层；
- 为 shard 已提供的 PE/PB/MA60/support/volume-zone 再上 Web；
- 已成功物化的同一 shard 再次读取。
- 将完整 shard 原文批量返回执行上下文，而不是在工具调用内部只投影目标公司事实。

`screening_groups_by_industry` 可以继续存在供其他流程使用，但 A股低风险买点榜主流程忽略它。

## 10. 执行审计

正式结果建议保存：

```json
"data_access_audit": {
  "routed_industry_count": 0,
  "universe_company_count": 0,
  "working_set_company_count": 0,
  "working_set_count": 0,
  "unique_shard_read_count": 0,
  "post_freeze_shard_read_count": 0
}
```

发布前要求：
- `working_set_company_count == universe_company_count`；
- `working_set_count == routed_industry_count`；
- `post_freeze_shard_read_count == 0`。

否则视为数据访问流程不完整，不得把执行路径描述为 canonical complete。

## 11. 一句话版本

> 趋势榜先选行业；company_industry_index 找全公司；去重 shard 后按小批次读取，并在工具调用内部立即解析、只抽取目标公司并投影为标准事实；全部事实收集齐后按行业动态生成本轮工作文件并锁定，后面的硬过滤、预筛、研究、估值和买点全部只围绕这些文件进行。

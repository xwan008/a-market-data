# A股低风险买点榜｜唯一主流程与数据职责

本文件定义“A股低风险买点榜”的唯一主流程和数据职责。若其他协议/Override 对“谁决定行业公司全集、哪些文件是事实源、哪些文件只是缓存、执行顺序”存在冲突，以本文件为准；其他文件继续负责各自阶段的具体判定标准。

## 1. 唯一主流程

```text
Trend Handoff
→ 三级行业路由
→ company_industry_index 展开行业全部策略公司
→ 读取公司事实
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

## 2. 数据职责必须分离

### 2.1 Trend Handoff：只决定研究哪些行业

`research/trend_handoff.json`

只负责：
- 当期新仓优先趋势；
- 对应申万三级行业代码；
- 趋势/市场状态透传。

不负责：
- 决定行业里有哪些公司；
- 个股硬过滤；
- 个股估值；
- 买入区间。

### 2.2 Universe：只由 company_industry_index 决定

`data/research/company_industry_index.json`

这是“某个三级行业有哪些策略公司”的唯一权威入口。

规则：
- resolved 三级行业后，必须从该索引展开全部策略公司；
- `screening_group_index.json` / `screening_groups_by_industry/*.json` 的缺失不得解释为行业无公司；
- 行业缓存只能加速，不能拥有准入权；
- 若索引有公司而缓存无该公司，必须回退到底层事实源读取，不能漏掉公司。

### 2.3 Facts：底层事实真源是 shard/runtime 原始字段

`data/shards/*.json` 是公司级完整事实真源，包含：
- 当前价格与基础行情；
- PE / dynamic PE / PB / market cap；
- ROE、收入、利润、扣非、现金流、毛利率等；
- MA20 / MA60；
- 60 日高低点、position_pct；
- support / resistance；
- dense / volume profile price zones；
- 行业映射。

正式结论不得因为缓存缺字段而假设事实不存在。

### 2.4 Industry compact view：只做性能缓存

`data/runtime/screening_groups_by_industry/*.json`

定位：
- 只是从已有 runtime facts 派生出的紧凑缓存；
- 用于一次读取同业常用估值、财务、质量和价格结构字段；
- 命中时优先使用以减少 I/O；
- 未命中或字段缺失时回退 `data/shards/*.json`；
- 不得决定行业公司全集；
- 不得因为公司不在缓存就标记 `NO_RUNTIME_CANDIDATE`、`NO_UNIVERSE_MEMBER` 或直接跳过。

## 3. 公司级执行顺序

### Stage A：展开与硬过滤

1. 根据 handoff 解析三级行业；
2. 用 `company_industry_index.json` 展开行业全部策略公司；
3. 优先从行业 compact cache 读取已有公司事实；
4. 缓存缺公司/缺关键字段时，按 shard 前缀去重回退读取 `data/shards/*.json`；
5. 执行公司级硬过滤。

### Stage B：轻量同业预筛

仅对 hard-eligible 公司做：
- 增长；
- 核心利润；
- 现金流/一次性收益质量；
- 估值；
- 60 日位置。

每三级行业原则上 Top5；第6名与第5名分差满足既定 tie 规则时可一起进入，最多 6 家。

### Stage C：Transmission

只对 pre-screen selected 公司研究未来 1–2 季度行业趋势是否能传导到公司盈利。

### Stage D：Expectation

只对 Transmission=SUPPORTED 的公司判断当前预期阶段。

### Stage E：Risk–Reward / Price Range

对需要闭合的公司按 `INDUSTRY_ADAPTIVE_VALUATION_OVERRIDE.md`：

```text
行业估值原型
+ 同业估值统计
+ 公司增长/ROE/盈利质量修正
→ fundamental_anchor_price

fundamental_anchor_price
+ MA60 / support / volume-zone
→ reasonable_price_range

reasonable_price_range
+ 行业与波动自适应安全边际
→ low_risk_buy_range
```

技术结构只负责择时，不得抬高基本面估值上限。

## 4. I/O 优先级

同一轮对每个 routed 三级行业按以下优先级取数：

```text
1. company_industry_index：确定完整公司名单
2. screening_groups_by_industry：批量缓存命中
3. data/shards：仅对缓存未命中公司/缺失字段做回退
4. Web：只补 Transmission / Expectation / 关键前瞻假设
```

禁止：
- 为缓存已具备的字段逐股重复读取 shard；
- 为 shard 已有字段再上 Web；
- 把 Web 作为价格结构数据源；
- 逐家公司重复读取同一 shard。

## 5. Cache completeness 不等于 Universe completeness

必须显式区分：

- `universe_company_codes`：来自 `company_industry_index`；
- `compact_cache_hit_codes`：行业缓存中实际命中的公司；
- `shard_fallback_codes`：因缓存缺失而回退 shard 的公司。

应满足：

```text
compact_cache_hit_codes ∪ shard_fallback_codes
== universe_company_codes（进入事实读取阶段的公司）
```

缓存覆盖率可以小于 100%，但 universe coverage 不允许因此下降。

## 6. 执行审计建议

正式结果可增加：

```json
"data_access_audit": {
  "routed_industry_count": 0,
  "universe_company_count": 0,
  "compact_cache_hit_count": 0,
  "shard_fallback_company_count": 0,
  "unique_shard_read_count": 0
}
```

异常：
- `shard_fallback_company_count` 接近全部 deep-research 公司且缓存本应具备字段；
- 同一 shard 被重复读取；
- company_industry_index 有公司但最终事实覆盖未包含；
- screening group 被当作 universe 权威来源。

## 7. 用户理解的一句话版本

> 趋势榜负责选行业；company_industry_index 负责找全公司；shard 提供底层事实；行业 compact 文件只负责把已有事实一次批量拿出来；预筛缩小研究范围；Transmission/Expectation 判断逻辑；行业自适应估值负责算买入区间。

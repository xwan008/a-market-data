# A-Market-Data

A股低风险买点榜 V2 数据与规则仓库。

## 设计原则

本仓库同时拥有 V2 所需的机械数据、更新链和唯一正式榜单规则。

正式榜单只消费：

- `data/snapshot.json`
- `skill/SKILL.md`

不依赖其他仓库的运行产物、GitHub Actions artifact、runtime bundle 或 commit SHA 门禁。

## V2 数据节奏

```text
每个交易日 16:30
行情 + 当日估值
        ↓
除权/拆分基准检查
        ↓
180日滚动K线
        ↓
趋势结构 + market_state
        ↓
shards + snapshot

每周日 18:00
全市场财务复核
        ↓
行业映射覆盖检查
        ↓
行业盈利状态重建
        ↓
重新生成 snapshot
```

日频只更新真正会快速变化的数据；慢变量不重复日抓。

## 数据目录

```text
data/latest.json                          # 当日行情、当日估值、最近一次验证财务
data/history_shards/*.json               # 180 个交易日滚动 K 线
data/trend_summary.json                   # K 线趋势/结构汇总
data/market_state.json                    # 每日市场环境
data/corporate_action_watch.json          # 除权/拆分基准调整记录
data/shards/*.json                        # 全市场机械数据分片
data/research/company_industry_index.json # 申万三级行业映射基线
data/research/industry_state.json         # 每周重建的三级行业盈利状态
data/snapshot.json                        # 正式榜单唯一机械数据入口
```

## 每日更新：16:30

GitHub Action：`.github/workflows/update-data.yml`

每日链只做：

1. 新浪 / 腾讯双源收盘行情；
2. 东方财富当日 PE / PB / 市值；
3. 财务字段沿用最近一次周度验证结果；
4. 对比供应商 `prev_close` 与仓库上一交易日收盘，识别除权、拆分等价格基准变化；
5. 必要时按新基准重标旧 OHLC，再追加当天 K 线；
6. 每只股票历史固定保留最近 180 个交易日，第 181 天写入时自动删除最旧一天；
7. 重建 5/20/60/120/180 日价格结构；
8. 生成 `market_state`；
9. 重建 shards 和 `snapshot.json`。

估值接口临时失败时允许沿用上一份已验证估值并标记 stale；单个外部估值源故障不会阻断 K 线日更。

## 每日 market_state

`market_state` 不依赖额外脆弱的指数接口，而是直接从本仓库全市场横截面和滚动历史机械生成：

- `trend`：MA20 参与度 + 个股 20 日收益中位数；
- `breadth`：上涨家数 / 有效样本；
- `liquidity`：全市场 `close × volume` 成交额代理相对过去 20 日中位数；
- `risk_level`：综合趋势、广度和流动性得到 `low / medium / high`。

它只用于正式榜单的风险修正，不作为硬性买卖开关。

## 每周更新：周日 18:00

GitHub Action：`.github/workflows/update-weekly-research.yml`

周频链负责慢变量：

1. 全市场财务报表字段重新抓取；
2. 当日/最近交易日估值同步复核；
3. 行业映射重新应用并要求覆盖率不低于 97%；
4. 根据行业内公司收入/利润同比及改善广度，机械重建 `industry_state.json`；
5. 重新生成并校验 `snapshot.json`。

行业映射本身不每周全量重爬；只有出现新股、映射缺失或覆盖率下降时才需要单独维护映射源。

## 确定性粗筛

粗筛只负责减少正式任务读取量：

- 行业盈利状态为 `improving`，或 `stable + divergent/broad`；
- 非 ST；
- 净利润为正；
- 财务与价格结构可用；
- 排除收入与利润同时严重坍塌的明显风险样本。

粗筛不做精确估值、不打总分、不决定买入、不排序。

## 稳定性边界

- 正式榜单不直接抓行情；
- 正式榜单不依赖 Actions artifact；
- 不做 SHA / runtime bundle 绑定；
- 不建立候选池、T2 池、周度池等跨期状态；
- 单只股票字段异常只影响该股票；
- 全市场覆盖明显异常时拒绝覆盖上一份有效数据；
- `snapshot.json` 目标体积不超过 3MB。

## 当前基线

首轮独立 V2 数据链已验证：

- 全市场：3177 只；
- 行情覆盖：100%；
- 财务覆盖：约 98.9%；
- 行业映射覆盖：约 98.8%；
- 确定性粗筛候选：435 只；
- `snapshot.json` 约 0.48MB。

旧仓库不再承担 V2 正式运行的数据依赖。

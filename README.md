# A-Market-Data

A 股低风险买点榜的数据与规则仓库。

## 设计原则

本仓库同时维护机械数据、更新链和正式榜单规则。

正式榜单以：

- `data/snapshot.json`
- `skill/SKILL.md`

作为机械数据与规则入口。

`snapshot.candidates` 是正式筛选的唯一机械候选池；行业景气、公司确认和估值阶段可以查询最新公开资料进行研究验证，但不得据此扩展候选池。

## 数据节奏

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

日频只更新真正会快速变化的数据；慢变量按周复核。

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
data/snapshot.json                        # 正式榜单唯一机械候选入口
```

## 每日更新：16:30

GitHub Action：`.github/workflows/update-data.yml`

每日链负责：

1. 新浪 / 腾讯双源收盘行情；
2. 东方财富当日 PE-TTM / 动态 PE / PB / 市值；
3. 财务字段沿用最近一次周度验证结果；
4. 识别除权、拆分等价格基准变化；
5. 必要时重标旧 OHLC，再追加当天 K 线；
6. 每只股票历史固定保留最近 180 个交易日；
7. 重建 5/20/60/120/180 日价格结构；
8. 生成 `market_state`；
9. 重建 shards 和 `snapshot.json`。

估值接口临时失败时允许沿用上一份已验证估值并标记 stale；单个估值源故障不会阻断 K 线日更。

## 每周更新：周日 18:00

GitHub Action：`.github/workflows/update-weekly-research.yml`

周频链负责：

1. 全市场财务报表字段重新抓取；
2. 当日/最近交易日估值同步复核；
3. 行业映射重新应用并检查覆盖率；
4. 根据行业内公司收入、利润同比及改善广度重建 `industry_state.json`；
5. 重新生成并校验 `snapshot.json`。

`industry_state` 代表已经兑现的行业盈利结果，不单独等同于未来行业景气。正式榜单运行时还会结合最新公开的价格、订单、库存、开工率、销量、出货、招投标、出口、产能利用率等适配领先变量进行行业景气复核。

## 确定性粗筛

机械粗筛只负责减少正式研究范围：

- 行业盈利状态为 `improving`，或 `stable + divergent/broad`；
- 非 ST；
- 股价 `<= 150` 元；
- `PE-TTM > 30` 直接剔除；
- `动态 PE > 30` 直接剔除；
- PE 两项任一超标即剔除；
- 净利润为正；
- 财务与价格结构可用；
- 排除收入与利润同时严重坍塌的明显风险样本。

粗筛不做精确估值、不打总分、不决定买入、不排序。

## 正式筛选流程

```text
snapshot.candidates
        ↓
行业景气复核
        ↓
同行择优
        ↓
公司确认
        ↓
价值判断
        ↓
买点确认
        ↓
市场风险修正
        ↓
排名发布
```

价值判断只输出两个价格结果：

- **合理区间**：保守至基准盈利假设对应的合理价值范围；
- **低风险区间**：在合理区间基础上加入适配安全边际后的低风险参与范围。

价格结构只决定当前是否适合执行，不反向修改合理区间或低风险区间。

## 当前基线

2026-09-07 最新数据：

- 全市场：3177 只；
- 行情覆盖：100%；
- 财务覆盖：约 98.9%；
- 行业映射覆盖：约 98.8%；
- 行业盈利粗筛后候选：579 只；
- 加入股价 / PE 硬上限后候选：256 只；
- `snapshot.json` 已通过完整性和硬上限校验。

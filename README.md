# A-Market-Data

A 股低风险买点榜的数据与规则仓库。

## 设计原则

本仓库同时维护机械数据、更新链和正式榜单规则。

正式运行时以：

- `data/runtime/meta.json`
- `meta.industry_state_file`
- `meta.screening_file`
- `meta.detail_file_template`
- `skill/RUNTIME_READ_PROTOCOL.md`
- `skill/SKILL.md`

作为当前榜单的数据与规则入口。

机械候选全集由 runtime screening 固定。公开资料只用于 deep research 验证行业、公司、盈利驱动和估值，不得据此扩展机械候选全集。

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
        ↓
runtime screening / details

每周日 18:00
全市场财务复核
        ↓
行业映射覆盖检查
        ↓
行业盈利状态重建
        ↓
重新生成 snapshot + runtime
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
data/snapshot.json                        # 数据生成源与兼容快照
data/runtime/meta.json                    # ChatGPT 正式 runtime 元数据与校验
data/runtime/industry_state_compact.json  # 全行业轻量输入
data/runtime/screening_snapshot.json      # 全机械候选轻量输入
data/runtime/details/{code}.json          # deep-read 单公司明细
skill/RUNTIME_READ_PROTOCOL.md            # runtime 信任边界和执行协议
skill/SKILL.md                            # 选股、估值、买点和排名规则
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
7. 重建价格结构；
8. 生成 `market_state`；
9. 重建 shards、snapshot 与正式 runtime。

估值接口临时失败时允许沿用上一份已验证估值并标记 stale；单个估值源故障不会阻断 K 线日更。

## 每周更新：周日 18:00

GitHub Action：`.github/workflows/update-weekly-research.yml`

周频链负责：

1. 全市场财务报表字段重新抓取；
2. 当日/最近交易日估值同步复核；
3. 行业映射重新应用并检查覆盖率；
4. 根据行业内公司收入、利润同比及改善广度重建 `industry_state.json`；
5. 重新生成并校验 snapshot 与 runtime。

`industry_state` 代表已经兑现的行业盈利结果，不单独等同于未来行业景气。正式榜单在 deep research 阶段仍需结合公开产业和公司证据验证未来 1–2 个季度逻辑。

## 确定性粗筛

机械粗筛只负责降低明显风险、减少正式 screening 范围：

- 行业盈利状态满足当前生成规则；
- 非 ST；
- 股价在机械上限内；
- PE-TTM / 动态 PE 在机械上限内；
- 净利润为正；
- 财务与价格结构可用；
- 排除收入与利润同时严重坍塌的明显风险样本。

粗筛不做精确估值、不打总分、不决定买入、不排序。

## 正式 screening 与 deep research

```text
validated runtime 全机械候选
        ↓
申万三级行业初始分组
        ↓
潜在结构相关性
support / volume zone / 60日位置
        ↓
同组三维非补偿比较
价格结构 / 估值质量 / 经营质量
        ↓
deep_read_codes
        ↓
公司主营 / 盈利驱动 / 行业传导确认
        ↓
正常化估值 + 最终安全区
        ↓
保守上下行空间
        ↓
最终排名发布
```

### screening 不做综合排名

形成 `deep_read_codes` 时禁止把行业、趋势、PE、PB、ROE、增长和价格位置压成一个可相互补偿的综合总分。

screening 先使用 runtime 的价格结构字段判断是否存在潜在结构相关性，再在同一申万三级行业内比较：

1. **价格结构**：支撑、成交密集区、60 日位置及结构风险；
2. **估值质量**：PE / PB 必须结合 ROE 和盈利增长解释；
3. **经营质量**：收入、利润、扣非、现金流及毛利率。

只有当同组另一家公司在三个维度都不明显更差，并至少一项明显更好，且不存在业务异质性或数据冲突需要进一步研究时，候选才允许在 deep-read 前被同行明确支配而排除。

如果三个维度互有胜负，不能用“综合排名较低”作为淘汰理由，应继续 deep-read。

### screening 结构线索不是最终安全区

screening 使用的 `support_center`、`volume_zone_center`、`position_pct` 只是研究准入线索。

最终 `low_risk_buy_range` 必须在 deep research 后，把：

- 正常化盈利；
- PE / PB 与 ROE、增长、现金流；
- 支撑 / 前低 / 成交密集区；

共同验证后形成。

因此价格结构不会被机械复制成最终价值底，也不会脱离估值单独决定正式买点。

## 审计重点

正式运行至少记录：

- `mechanical_candidate_count`
- `industry_coverage_count`
- `structural_relevance_count`
- `peer_dominated_count`
- `deep_read_codes_count`
- `company_confirmed_count`
- `research_uncertain_count`
- `waiting_count`
- `final_recommendation_count`

其中，`peer_dominated_count` 对应的候选应能够解释“由哪只同行替代，以及价格结构、估值质量、经营质量为何构成明确支配”。

审计指标只用于解释研究质量，不作为额外熔断器；整轮是否停止只服从 `RUNTIME_READ_PROTOCOL.md` 的 Runtime Hard Gate。
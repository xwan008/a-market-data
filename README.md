# A-Market-Data

A股低风险买点榜 V2 数据与规则仓库。

## 设计原则

本仓库同时拥有 V2 所需的机械数据、每日数据更新链和唯一正式榜单规则。

正式榜单只消费：

- `data/snapshot.json`
- `skill/SKILL.md`

不依赖其他仓库的运行产物、GitHub Actions artifact、runtime bundle 或 commit SHA 门禁。

## V2 主链

```text
新浪 / 腾讯行情 + 东方财富财务/估值
                 ↓
      data/latest.json
                 ↓
  本仓库滚动 K 线 history_shards
                 ↓
  趋势结构 + 行业映射 + 确定性粗筛
                 ↓
        data/snapshot.json
                 ↓
          单一 SKILL
                 ↓
盈利复核 → 估值/安全边际 → 价格位置 → 排名发布
```

## 数据目录

```text
data/latest.json                         # 当日全市场行情与基础财务
data/history_shards/*.json              # 本仓库滚动 K 线历史
data/trend_summary.json                  # K 线趋势/结构汇总
data/shards/*.json                       # 面向构建器的全市场分片
data/research/company_industry_index.json # 申万三级行业映射基线
data/research/industry_state.json        # 三级行业盈利状态基线
data/snapshot.json                       # 正式榜单唯一机械数据入口
```

历史 K 线、当前行情分片、行业映射与行业状态已从旧系统完成一次性迁移，后续正式数据链不再 checkout 旧仓库。

## 代码目录

```text
.github/workflows/update-data.yml        # 唯一每日数据工作流
scripts/fetch_market_resilient.py        # 双行情源 + 财务/估值抓取
scripts/history_store.py                 # 追加并维护滚动 K 线
scripts/build_history.py                 # 趋势摘要
scripts/build_bridge.py                  # 全市场分片
scripts/enrich_shards_with_industry.py   # 行业映射
scripts/restore_valuation_fallback.py    # 估值源临时失败时使用上一份已验证估值
scripts/build_snapshot.py                # 确定性粗筛并生成轻量快照
scripts/validate_snapshot.py             # 快照完整性与体积检查
skill/SKILL.md                           # 唯一正式榜单规则
```

## 每日更新

GitHub Action：`.github/workflows/update-data.yml`

- 工作日 16:20（Asia/Shanghai）运行；
- 支持手动 `workflow_dispatch`；
- 行情使用新浪/腾讯双源；
- 财务/估值来自东方财富公开接口；
- 只有完整收盘数据通过质量 Gate 才写入仓库；
- 估值接口临时不可用时允许沿用上一份已验证估值，并写入 `valuation_stale_fallback` 标记；
- 行情、K 线和财务不会因为单次估值接口故障而被整体阻断；
- 开发期新的同类验证运行会取消旧运行，避免重复抓取。

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
- 单只股票字段异常只淘汰该股票；
- 全市场数据明显异常时拒绝覆盖上一份有效数据；
- `snapshot.json` 目标体积不超过 3MB。

## 当前基线

迁移与首轮 V2 构建基线：

- 全市场：3177 只；
- 三级行业：92 个；
- 确定性粗筛候选：435 只；
- `snapshot.json` 约 0.48MB。

旧仓库不再承担 V2 正式运行的数据依赖。删除旧仓库前，只需确认本仓库最新一次 `Update V2 Market Data` 完整运行成功。

# A-Market-Data

A股低风险买点榜 V2 数据与规则仓库。

## 设计原则

本仓库只做两件事：

1. 把外部/共享市场数据整理成稳定、轻量、可直接消费的 `data/snapshot.json`；
2. 用一个 `skill/SKILL.md` 定义榜单判断规则。

旧仓库 `xwan008/a-share-market-data` 暂时作为共享机械数据上游，继续提供行情、K线和基础财务数据。V2 不复制旧仓库的研究流水线、runtime snapshot、artifact bundle、multi-skill gate 等复杂机制。

## V2 主链

```text
upstream market data
        ↓
build_snapshot.py
        ↓
data/snapshot.json
        ↓
SKILL.md
        ↓
候选筛选 → 估值判断 → 价格位置判断 → 排名发布
```

## 目录

```text
.github/workflows/update-data.yml   # 唯一数据更新工作流
scripts/build_snapshot.py           # 从共享数据源生成轻量快照
scripts/validate_snapshot.py        # 快照最低完整性检查
skill/SKILL.md                      # 唯一榜单规则
data/snapshot.json                  # 正式榜单唯一机械数据入口（由 Action 生成）
```

## 上游数据

当前默认上游：`xwan008/a-share-market-data@main`

优先复用：
- `data/shards/*.json`：现价、OHLC、基础财务、短周期趋势；
- `data/history_shards/*.json`：历史K线（需要更长价格结构时按需读取）；
- `data/research/industry_state.json`：仅作为迁移期可选行业状态来源，不继承旧研究流程。

## 边界

- 正式榜单不直接运行数据抓取脚本；
- 正式榜单不依赖 GitHub Actions artifact；
- 不做 commit SHA 与运行包双重绑定；
- 不建立候选池/T2池/周度池等跨期中间状态；
- 数据异常时只阻止本次 `snapshot.json` 更新，不破坏上一份有效快照。

# A-Market-Data

A股低风险买点榜 V2 数据与规则仓库。

## 设计原则

本仓库只做两件事：

1. 把共享市场数据压缩成稳定、轻量、可直接消费的 `data/snapshot.json`；
2. 用一个 `skill/SKILL.md` 定义正式榜单判断规则。

旧仓库 `xwan008/a-share-market-data` 暂时只作为共享机械数据上游，提供行情、K线衍生结构、基础财务和迁移期行业状态。V2 不继承旧仓库的研究流水线、runtime snapshot、artifact bundle、multi-skill gate 等机制。

## V2 主链

```text
旧仓库共享机械数据
        ↓
确定性粗筛 + 数据压缩
        ↓
data/snapshot.json
        ↓
单一 SKILL
        ↓
盈利复核 → 估值/安全边际 → 价格位置 → 排名发布
```

## 当前目录

```text
.github/workflows/update-data.yml   # 唯一数据更新工作流
scripts/build_snapshot.py           # 构建轻量候选快照
scripts/validate_snapshot.py        # 快照最低完整性/体积检查
skill/SKILL.md                      # 唯一正式榜单规则
data/snapshot.json                  # 正式榜单唯一机械数据入口
```

## 当前数据策略

上游：`xwan008/a-share-market-data@main`

只稀疏读取：

- `data/shards/*.json`：现价、基础财务、60日价格结构；
- `data/research/industry_state.json`：迁移期三级行业盈利状态。

V2 不复制旧仓库完整历史数据，也不在正式榜单运行时读取 `history_shards`。需要的 K 线信息先在数据层压缩成 `price_structure`。

当前粗筛是确定性的，只负责减少读取量：

- 行业 `improving`，或 `stable + divergent/broad`；
- 非 ST；
- 净利润为正；
- 财务与价格结构可用；
- 排除收入与利润同时严重坍塌的明显风险样本。

粗筛不做估值、不打分、不决定买入、不排序。

## 更新方式

GitHub Action：`.github/workflows/update-data.yml`

- 交易日工作日 16:20（Asia/Shanghai）运行；
- 支持手动 `workflow_dispatch`；
- 修改 `scripts/`、`skill/` 或工作流自身时也会自动验证一次；
- `data/snapshot.json` 的提交不会再次触发工作流，因此不会形成循环。

## 稳定性边界

- 正式榜单不直接抓行情；
- 正式榜单不依赖 GitHub Actions artifact；
- 不做 commit SHA 与运行包绑定；
- 不建立候选池/T2池/周度池等跨期中间状态；
- 单只股票字段异常只淘汰该股票；
- 只有全市场覆盖明显异常才阻止更新；
- 快照目标体积不超过 3MB。

## 当前验证结果

首轮 V2 已跑通：

- 全市场：3177 只；
- 三级行业：92 个；
- 确定性粗筛后候选：435 只；
- 快照体积约 0.48MB。

这意味着正式榜单运行时不再扫描整个旧仓库，只读取一个轻量快照和一个规则文件。

# A股趋势买点榜

**运行目标：从行业趋势中寻找值得参与的公司、可观察的趋势萌芽信号、经过确认的入场计划，以及判断错误后的退出边界。**

## 唯一主流程（main）

```text
A股板块趋势榜 → research/trend_handoff.json
→ data/low_risk/index.json + 各行业 manifest/parts → 冻结公司池
→ 公司硬过滤 → Python 对所有合格公司计算紧凑量价与基本面机会分
→ 每申万三级行业前置动态 Top5（必要时并列第6）
→ 仅对入选公司核查真实主题传导、财务与业务风险；必要时同行候补
→ scripts/trend_buy_engine.py：READY / WAIT / UNCERTAIN / DROP
→ 跨三级行业每主题动态0–5只买点候选和一只优先关注股
→ research/trend_buy_formal_result.json（完整 Gate 后正式提交并回读）
→ research/trend_buy_handoff.json（只投影主题Top5，核对SHA后提交并回读）
→ research/intraday_market_snapshot.json → research/intraday_monitor_state.json
```

**没有额外的V3榜单或备用选股流程。** 算法调整直接更新主分支上的 canonical 规则和正式程序。现有接口字段 `trend_buy_result_v2`、`trend_buy_handoff_v2` 和 `trend_buy_v2` 是为下游盘中任务保留的数据格式名称，**并非第二套选股策略**。

**研究边界：** 公司预筛使用增长、质量、估值匹配及技术机会；先对全部合格公司做Python轻量扫描，再按70%买点机会+30%原基本面分限制深度研究名额。MA60不是单项淘汰红线；COOLING不代表持仓强制卖出。业务证据缺失就阻断正式发布，不使用旧榜替代、不把试算冒充正式买点。

**盘中安全边界：** 仅接受与当期正式 `top5_by_theme` 完全对应的handoff。如果历史正式结果不带动态Top5，盘中交易监控暂停该部分信号并要求重新完成正式研究，不允许退回旧的全部READY/WAIT名单。

## 三个自动任务

- **A股板块趋势榜**：周一至周五北京时间06:40、18:40；维护`trend_registry.json`与`trend_handoff.json`，并核验交易所日历。
- **A股趋势买点榜**：周一至周五北京时间07:00、19:00；早间隔夜复核，晚间完整研究和正式结果发布。
- **A股盘中交易执行监测**：按既定盘中时段，读取已冻结快照、监测交易条件、持仓风险和市场分歧。不自动下单。

## 主要规则和代码

- [趋势买点主规则](skill/TREND_BUY_CANONICAL.md)
- [公司预筛](skill/PRE_SCREEN_RESEARCH_SCOPE_OVERRIDE.md)
- [行业路由](skill/TREND_HANDOFF_ROUTING_OVERRIDE.md)
- [板块趋势管理](skill/TREND_REGISTRY_PROTOCOL.md)
- [盘中执行](skill/INTRADAY_MONITOR_CANONICAL.md)
- `scripts/build_full_market_price_structure.py`：全市场完成日K的结构分析
- `scripts/trend_buy_engine.py`：公司状态、确认买点与早期关注股的计算
- `scripts/trend_buy_handoff.py`：生成正式交易交接数据
- `scripts/build_intraday_snapshot.py`：盘中快照和来源完整性校验

## 数据发布与验证

正式版从公司冻结池、来源证据、全部入选覆盖、价格结构一致性、风险计划和JSON schema通过校验后发布。先提交正式结果并从main完整READBACK取得Git blob SHA，再投影正式READY/WAIT名单为handoff，提交及READBACK后才报告成功。

- [当前正式结果](research/trend_buy_formal_result.json)
- [当前交易交接](research/trend_buy_handoff.json)
- [主流程持续回归测试](.github/workflows/validate-trend-buy.yml)

研究建议均带有交易日时间戳；早期关注和条件入场并不保证收益。跳空、涨跌停、流动性和滑点可能导致真实损失超出计划。

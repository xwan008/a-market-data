# A股趋势买点榜

**运行目标：从行业趋势中寻找值得参与的公司、可观察的趋势萌芽信号、经过确认的入场计划，以及判断错误后的退出边界。**

## 业务链路

```text
A股板块趋势榜（行业状态与优先方向）
  → research/trend_handoff.json
  → data/low_risk/index.json + 行业manifest/parts
  → Frozen Working Set + 公司硬过滤 + 同业预筛
  → 业务关联、经营与财务风险核验
  → data/research/full_market_price_structure.json（日K、量价与风险结构）
  → scripts/trend_buy_engine.py
      ├─ READY：已确认的BREAKOUT / PULLBACK条件入场计划
      ├─ WAIT：等待量价或板块确认
      ├─ UNCERTAIN / DROP：资料不足或资格失效
      └─ READY=0时：各板块一只EARLY_FOCUS_NOT_READY研究关注股
  → research/trend_buy_formal_result.json
  → research/trend_buy_handoff.json（正式READY/WAIT交易计划）
  → research/intraday_market_snapshot.json
  → research/intraday_monitor_state.json
```

**数据时间要求：** 价格结构、公司身份和研究证据与相应的已完成交易日一致。公司筛选采用同业增长、盈利质量、估值匹配、趋势健康度，并完整覆盖每个上游行业Top5、并列第6的研究集合。PE/PB用于公司风险比较，入场与失效价格由量价结构生成。

## 两种观察视角

**确认买点 READY：** 行业趋势与个股入场形态、商业证据和风险审查都通过时，产生下一交易日有价格上限的条件性交易计划，包括`entry_zone`、`entry_trigger`、`max_entry_price`、`invalidation_price`、`initial_risk_pct`、`exit_plan`。

**趋势萌芽期重点关注：** READY为0时，每个有合格WAIT的板块优先选出一只`EARLY_FOCUS_NOT_READY`。研究同日1日/5日量比、20日相对强弱、MA20斜率、收盘强度和抬高低点，提出参考触发价、需要补齐的量价证据及可核验的风控参考；缺失可信支撑时只报告观察条件，不生成可执行买入区。关注股始终保留WAIT状态，不直接授权盘中买入。

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
- [趋势模型持续回归测试](.github/workflows/validate-trend-buy-v2.yml)

研究建议均带有交易日时间戳；早期关注和条件入场并不保证收益。跳空、涨跌停、流动性和滑点可能导致真实损失超出计划。

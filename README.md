# A股趋势买点榜｜唯一正式运行版本

> 2026-10-10起替代「A股低风险PE买点榜」。本仓库只有**一套活跃公司买点逻辑**：**趋势发现 → 公司筛选 → 趋势买点确认 → 结构风险计划 → 盘中监测**。旧估值买点榜及原正式数据已经退役，历史可通过 Git 记录查询。

## 研究目标

从已核实行业趋势中筛选具有真实业务关联、基本面风险可接受的股票，确认突破或回踩承接入场，明确入场区、最高允许买价、结构失效位、下行风险和退出纪律。

PE/PB、盈利质量、MA60仅用于公司过滤或风险评估，**不能直接生成买入区**。股票涨得好不代表应该追，价格进入支撑区也不代表回调已确认。只有完成本轮收盘日K线验证、公司风险核查且具有可执行的次日入场计划，才可能成为READY。

## 唯一真实运行链

```text
A股板块趋势榜
  → research/trend_handoff.json
  → data/low_risk/index.json + 各行业manifest/part
     （low_risk只是物化公司池的历史技术路径，不是一份并行榜单）
  → 公司硬过滤及0.45增长/0.25质量/0.20估值匹配/0.10趋势健康预筛
  → 同业Top5，分差≤0.03可入选第6
  → 真实公司业务关联和风险核查
  → data/research/full_market_price_structure.json（当日完成日K）
  → BREAKOUT / PULLBACK交易结构及执行计划
  → research/trend_buy_formal_result.json
  → research/trend_buy_handoff.json （仅READY/WAIT）
  → research/intraday_market_snapshot.json
  → research/intraday_monitor_state.json
```

唯一正式总规则：**[skill/TREND_BUY_CANONICAL.md](skill/TREND_BUY_CANONICAL.md)**。
辅助业务规则：[公司预筛](skill/PRE_SCREEN_RESEARCH_SCOPE_OVERRIDE.md)、[行业路由](skill/TREND_HANDOFF_ROUTING_OVERRIDE.md)、[上游趋势状态](skill/TREND_REGISTRY_PROTOCOL.md)、[盘中执行](skill/INTRADAY_MONITOR_CANONICAL.md)。

核心可执行代码：
- `scripts/build_full_market_price_structure.py`：在数据生产层用全市场日K计算突破、回踩、量价、追高风险及结构失效；
- `scripts/trend_buy_engine.py`：输入当轮完成研究的候选及**同日**价格结构，输出READY/WAIT/UNCERTAIN/DROP、入场计划；
- `scripts/trend_buy_handoff.py`：将成功提交并回读的正式结果投影为唯一的交易交接对象；禁止旧估值区间字段；
- `scripts/build_intraday_snapshot.py`：**仅接受**正式V2 handoff，校验Git blob SHA、run_id、trade_date及逐股合同；失败不回退旧榜。

最终状态：
- READY：收盘结构已确认，但只允许下一有效交易日按入场区和最高允许价执行；不代表无条件市价买；
- WAIT：等待突破、回调、确认或风险收益改善；
- UNCERTAIN：业务或K线日期/内容证据不足；
- DROP：主题关联或结构性资格已失效。

## 三个定时任务

- **A股板块趋势榜**：北京时间工作日06:40、18:40，严格官方交易日校验；
- **A股趋势买点榜**：北京时间工作日07:00、19:00，07:00隔夜核查，19:00完整收盘研究及正式发布；
- **A股盘中交易执行监测**：原盘中时段不变，仅读正式新版快照和已有持久化监控状态，不下单、不重新选股。

**发布Gate**：公司行业身份、工作集冻结、全量预筛/公司研究、证据时间、同日完整K线、入场区和失效价审计需全部通过；JSON写前解析，写GitHub后必须commit及逐字段READBACK，正式handoff须匹配最终result的真实blob SHA。失败不能覆盖最后有效V2结果，更不能回退旧PE榜。

## 首次新版基线

在第一次完整正式新榜通过前，`research/trend_buy_formal_result.json` 与 `research/trend_buy_handoff.json` 为 **BASELINE_UNAVAILABLE** 占位状态，不代表已发布买点。盘中行情生产和定时任务应给出 NO_VALID_TREND_BUY_HANDOFF/MORNING_HANDOFF_UNAVAILABLE，不把历史旧股票信号冒充当天判断。后续按单版本规则持续迭代参数，不恢复双榜。

## 回归测试与历史留痕

[唯一版本CI](.github/workflows/validate-trend-buy-v2.yml) 覆盖形式化正式发布、handoff Git SHA、旧字段拒绝、回踩/突破信号与10月9日历史K线回放。历史回放仅用于验证计算，不构成当日正式推荐。

[退役历史说明](research/archive/LOW_RISK_PE_RETIRED_2026-10-10.md) 记录了最后一份旧PE榜与handoff的原始Git blob SHA；原活动文件已删除，仍可通过Git历史审计。

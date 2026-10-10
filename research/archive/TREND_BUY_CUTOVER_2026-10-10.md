# A股趋势买点榜｜2026-10-10 单版本切换记录

状态：**SOLE_VERSION_CUTOVER_COMPLETE / FIRST_FRESH_BASELINE_PENDING**。

## 定时任务

已在原有三个ChatGPT定时任务原位更新，不创建重复任务：
- 上游“A股板块趋势榜”：06:40/18:40 Asia/Shanghai 原排程与产业/市场趋势双链不变；只交接 research/trend_handoff.json；
- 公司榜：已由“A股低风险买点榜”原位更名为 **“A股趋势买点榜”**，07:00/19:00 Asia/Shanghai 原排程不变；完整公司研究后只使用唯一规则 skill/TREND_BUY_CANONICAL.md 与 BREAKOUT/PULLBACK价格确认；19:00成功完整发布后才写正式result/handoff；
- “A股盘中交易执行监测”：原时段不变；只接受 trend_buy_handoff_v2 经Git SHA验证的快照，读取trend_buy_stocks；无新版基线时明确中止相关股票信号，不读取旧榜。

## GitHub 单一路径

- 主规则：skill/TREND_BUY_CANONICAL.md（PRODUCTION_CANONICAL）
- 公司过滤与同业预筛：skill/PRE_SCREEN_RESEARCH_SCOPE_OVERRIDE.md（公司过滤，不是买点）
- 行业趋势源：research/trend_handoff.json
- 同日已完成全市场OHLCV：data/research/full_market_price_structure.json
- 买点计算：scripts/trend_buy_engine.py；正式 Gate 标记 mode=FORMAL 和全套审计字段必须通过
- 正式结果：research/trend_buy_formal_result.json
- 唯一正式股票交接：research/trend_buy_handoff.json
- 盘中股票字段：research/intraday_market_snapshot.json 的 trend_buy_stocks，结构计划 trend_entry_plan
- 盘中唯一状态：research/intraday_monitor_state.json（首次以V2重建）

## 已彻底退出活跃路径

已删除旧 research/latest_formal_result.json、research/low_risk_handoff.json、旧估值/安全边际主规则、旧估值影子引擎/CI、旧低风险信号历史对账CI和旧盘中快照/旧state。退役前版本可通过Git历史查询，参见LOW_RISK_PE_RETIRED_2026-10-10.md。

data/low_risk/index.json及目录只是**历史技术命名的物化公司事实池**，仍为趋势榜的合规公司筛选来源；不是第二份业务榜。

## 校验

- 正式V2引擎、PRECHECK/Gate、READY与WAIT状态、突破与回调、公司冻结价一致性、次日入场上限、GitHub blob SHA/身份关联、旧合同不准进入盘中：已有自动化回归测试。
- GitHub Actions成功验证：https://github.com/xwan008/a-market-data/actions/runs/38027145757 ，历史真实3177只股票结构与42家公司10/9回放用于计算正确性审计，不冒充新正式买点。
- 退役后所有唯一版本文档与定时任务指令已同步。未建立第二个公司榜定时任务。

## 当前没有首份有效正式买点的事实

截至切换完成，正式 result/handoff 均为 **BASELINE_UNAVAILABLE** 占位，`trade_date=null`，没有可执行股票信号，绝不应把它们称为COMPLETE。下一轮真实完整交易日研究、数据一致性与GitHub提交回读均通过后，才更新正式榜单和交接；此前早间/盘中报告无有效基线，**不回退旧PE榜**。策略价格阈值会在后续实际运行中根据假突破、跳空、交易成本及回撤复盘逐步修订，但严格覆盖、日期、来源和真实提交/回读门槛保留。

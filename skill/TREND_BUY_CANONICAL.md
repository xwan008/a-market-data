# A股趋势买点榜｜唯一正式业务规则（2026-10-10 起）

**状态：PRODUCTION_CANONICAL。** 此文件是原“A股低风险PE买点榜”的**唯一替代**。不存在双引擎、双榜或自动回退旧估值版本。历史低风险榜及其规则只可作为 Git 版本历史查阅，不得在当前决策、发布、监控或失败恢复中引用。技术阈值为可修正的初始参数，不代表已经证明有超额收益。

## 1. 唯一目标

从已核实的行业趋势出发，选择真实业务关联且公司质量/风险可接受的候选股票，识别**完成交易日K线确认**的突破/回踩买点，给出**次日允许的入场区间、最高追价、结构失效价、退出条件、初始价格风险**。没有买点就 WAIT，没有可靠数据就 UNCERTAIN，结构或业务严重失效就 DROP，绝不为凑READY而推测。

公司基本面 / PE / PB / MA60 / 历史位置是**公司过滤、同业比较和风险识别**，不是估值折价买价。不能以“便宜”或“离MA60近”自动标记 READY。趋势买点与企业公允价值不同，失效价格是执行纪律，不保证实际成交止损。

## 2. 唯一执行链

1. 使用 research/trend_handoff.json，按 skill/TREND_HANDOFF_ROUTING_OVERRIDE.md 路由行业；时间以 Asia/Shanghai 为准，官方A股交易日校验。早7:00用严格前一完整交易日，晚19:00用当日完整收盘；非交易日自动任务停止，不把旧日期冒充当前。
2. 读取 data/low_risk/index.json（这是**公司冻结池的旧技术目录名**，不代表旧榜仍在运行），逐行业读取一次manifest和所有parts，校验日期、身份、成员、字节、完整性；构造working set后Freeze，禁止回读shard/index/part补充冻结字段。
3. 依据 skill/PRE_SCREEN_RESEARCH_SCOPE_OVERRIDE.md 对全部公司硬过滤和同业预筛：0.45增长传导代理+0.25质量+0.20 PE/PB与增长匹配+0.10趋势健康；每行业Top5，分差≤0.03可第6。审计完整的Universe、未入选名单、公司覆盖率，未完成不得发布。
4. 对全部入选公司完成本轮公司业务关联/风险核查：SUPPORTED=有可核实的商业传导；EARLY_EVIDENCE=主题相关研发/客户测试有事实但盈利未兑现，允许继续评估交易结构但需额外核实风险；UNCERTAIN=证据缺失/冲突，NOT_SUPPORTED=直接业务联系被证伪。公司盈利和现金流的实质性风险可能阻断READY，但不得靠PE/MA60生成入场位。
5. 从已完成日K生成并持久化的 data/research/full_market_price_structure.json 获取结构（scripts/build_full_market_price_structure.py）。交易日必须等于冻结池trade_date；每个候选≥120根有效已完成日K，data_status=verified，data_date与price一致；同日冻结收盘价与结构价偏差超过合理精度该公司UNCERTAIN，不能回退旧值。
6. 使用 scripts/trend_buy_engine.py 的 `trend_buy_research_v2 → trend_buy_result_v2` 逻辑。仅确认 BREAKOUT（历史60/120日前高、放量、收盘位置）或 PULLBACK（上升结构、MA20回踩、收盘承接）两类结构。必须明确 entry_zone、max_entry_price、entry_trigger、invalidation_price、invalidation_rule、initial_risk_pct、exit_plan；待触发WAIT可以给条件区，不将其称作当天有效买点。
7. 完成发布前审计：fresh_company_research、working_set_frozen、pre_screen_coverage、company_research_coverage、structure_same_day、no_future_evidence、json_schema_valid 全部true；以及source-review、价格和状态一致。**无合法COMPLETE结果就报告失败，并让盘中标记“本轮趋势榜不可用”；绝不回退历史低风险榜。**
8. 正式结果唯一写 research/trend_buy_formal_result.json，schema `trend_buy_result_v2`，包含明确run_id、trade_date、READY/WAIT/UNCERTAIN/DROP及审计。写前JSON序列化+反解析+完整Gate；GitHub提交后从main回读内容、SHA、run_id、名单逐项一致。
9. 仅19:00完整正式研究发布后，取已readback正式结果的真实 blob SHA，投影 scripts/trend_buy_handoff.py 的 `trend_buy_handoff_v2`，**唯一写 research/trend_buy_handoff.json**。HANDOFF只含READY+WAIT，完全保留股票身份、交易计划和rank，禁止出现 `reasonable_buy_range`、`low_risk_buy_range`。写后READBACK比对。早7:00只是隔夜信息复核，不写handoff；人工明确要求完整收盘版且Gate全部通过时可更新。
10. 盘中唯一读取 research/intraday_market_snapshot.json，并确认其 source_stock_handoff_path 为 research/trend_buy_handoff.json、stock_handoff_kind=trend_buy_v2、schema/run_id/日期/名单完全一致后执行 skill/INTRADAY_MONITOR_CANONICAL.md。盘中不重新选股，不改入场价，不用历史“估值买点”补价，不自动下单。

## 3. 初始交易规则（继续运行中校准）

- BREAKOUT：当日收盘站稳前60/120日关键阻力（不含当日K线），当日/近5日量比确认且收盘在当日振幅位置≥55%；距MA20明显过大不追，跳空超max_entry_price取消买入。
- PULLBACK：已确认上升结构、higher_low、MA20附近实际触及、收盘重新站上MA20且高于前收盘并形成较强承接；仅碰到均线不是买点。
- 风控初值：入场区间上沿到失效价的价格距离上限6%；收盘距MA20>8%或chase=high时不追；已知合理上方阻力若不足1.5R暂缓；默认下一交易日最多1.2%执行价格容差。**这些均是试运行参数，后续根据假突破、最大回撤、换手、跳空、手续费实证调整。** 不知道上方阻力不能伪造涨幅目标。
- 价格区与失效价只是计划；实盘跳空、涨跌停、成交滑点可导致更大亏损；仓位按账户可承受错误成本决定。
- EXIT：①商业逻辑被证伪；②确认结构失效/突破失败；③市场/行业趋势衰退与个股转弱共振；④上涨后结构保护位上移及分批退出。盘中暂时跌破与收盘确认分开处理；持仓与空仓使用不同规则。不得因为价格反弹到成本价就机械清仓。

## 4. 状态与字段

- READY：公司研究完成，入场结构已确认，下一交易日存在具风险边界的条件执行计划。不是即时无条件买入。
- WAIT：等待突破/回调/进一步确认/风险改善，`wait_reason` 只允许 WAIT_BREAKOUT / WAIT_PULLBACK / WAIT_CONFIRMATION / WAIT_RISK_REWARD。WAIT理由必须可理解；待触发区间不等于已经满足入场条件。
- UNCERTAIN：公司业务、K线/成交或日期口径缺口，不能给可信计划。
- DROP：公司业务关联反证、重大风险硬过滤，或明确结构损毁且不再可研究。
- EARLY_EVIDENCE 不能自动升级为商业化SUPPORTED，但可以在充分直接业务证据和额外经营风险复核后研究趋势买点。禁止把主营其他合同冒充主题商业兑现。

状态按行业/公司、来源时间、情景风险、价格证据全覆盖。READY/WAIT依正式引擎保证具有必填参数；handoff不许保留旧估值区间字段。

## 5. 唯一版本与异常原则

原 low-risk 正式结果、handoff、对应历史规则和影子估值研究**已退役**；仓库 Git 历史及研究归档可追溯，但**没有活跃第二榜单**。每日定时任务名称“A股趋势买点榜”，周一至周五北京07:00/19:00原时段。上游“A股板块趋势榜”06:40/18:40及盘中执行监测原时段保持不变，仍通过交易日Gate。

旧路径 research/latest_formal_result.json 和 research/low_risk_handoff.json 不可再被读取为生产研究或盘中状态来源。若当天新版正式结果还未有效发布（例如首个早间没有基线），则报告 MORNING_HANDOFF_UNAVAILABLE / NO_VALID_TREND_BUY_HANDOFF；不能将历史低风险记录改名冒充新榜。

每次失败记录具体阶段、工具、readback/commit与真实错误；权限或安全拒绝不得换工具规避。失败不覆盖最后一份**同版本且时间适用**的COMPLETE正式结果，也不以旧数据冒充新日期。完整审计通过后才称PERSISTED。

正式业务流程不再读 skill/LOW_RISK_CANONICAL_FLOW.md、skill/PRICE_RANGE_OUTPUT_OVERRIDE.md、skill/INDUSTRY_ADAPTIVE_VALUATION_OVERRIDE.md、skill/SKILL.md 的旧状态/估值买价规则；以本文件为唯一公司研究与买点主规则。其余旧研究文件只保留存档用途，不可与本文件“合并生效”。

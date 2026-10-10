# A股趋势买点榜｜唯一正式业务规则（2026-10-10 起）

**状态：PRODUCTION_CANONICAL。** 本文件定义“A股趋势买点榜”完整研究与发布流程。技术阈值可依据运行证据持续修正，尚不代表已证实超额收益。

## 1. 唯一目标

从已核实的行业趋势出发，选择真实业务关联且公司质量/风险可接受的候选股票，识别**完成交易日K线确认**的突破/回踩买点，给出**次日允许的入场区间、最高追价、结构失效价、退出条件、初始价格风险**。没有买点就 WAIT，没有可靠数据就 UNCERTAIN，结构或业务严重失效就 DROP，绝不为凑READY而推测。

公司基本面、PE/PB、MA60与历史位置用于公司过滤、同业比较和风险识别。入场价由实际量价结构与触发条件形成，READY必须通过完整验证；结构失效价格属于执行风险边界，不保证实际止损成交价。

## 2. 唯一执行链

1. 使用 research/trend_handoff.json，按 skill/TREND_HANDOFF_ROUTING_OVERRIDE.md 路由行业；时间以 Asia/Shanghai 为准，官方A股交易日校验。早7:00用严格前一完整交易日，晚19:00用当日完整收盘；非交易日自动任务停止，不把旧日期冒充当前。
2. 读取 `data/low_risk/index.json`，逐行业读取一次manifest和全部parts，校验日期、身份、成员、字节及完整性；构造working set并Freeze，后续研究只使用冻结的数据事实。
3. 依据 skill/PRE_SCREEN_RESEARCH_SCOPE_OVERRIDE.md 对全部公司硬过滤和同业预筛：0.45增长传导代理+0.25质量+0.20 PE/PB与增长匹配+0.10趋势健康；每行业Top5，分差≤0.03可第6。审计完整的Universe、未入选名单、公司覆盖率，未完成不得发布。
4. **上游板块确认门槛：** Trend Handoff的每个板块必须冻结并传递 `trend_state`、`market_state`。只有市场状态为**趋势确认**的板块才允许个股进入READY；“候选趋势”即使个股突破/回调形态确认，也只能WAIT_CONFIRMATION，禁止越过板块确认擅自下单。对高潮/衰退、失效状态按风险证据降低优先级。板块研究和状态只由原板块趋势榜改变，下游买点任务无权替上游升级。
5. 对全部入选公司完成本轮公司业务关联/风险核查：SUPPORTED=有可核实的商业传导；EARLY_EVIDENCE=主题相关研发/客户测试有事实但盈利未兑现，允许继续评估交易结构但需额外核实风险；UNCERTAIN=证据缺失/冲突，NOT_SUPPORTED=直接业务联系被证伪。公司盈利和现金流的实质性风险可能阻断READY，但不得靠PE/MA60生成入场位。
6. 从已完成日K生成并持久化的 data/research/full_market_price_structure.json 获取结构（scripts/build_full_market_price_structure.py）。交易日必须等于冻结池trade_date；每个候选≥120根有效已完成日K，data_status=verified，data_date与price一致；同日冻结收盘价与结构价偏差超过合理精度该公司UNCERTAIN，不能回退旧值。
7. 使用 scripts/trend_buy_engine.py 的 `trend_buy_research_v2 → trend_buy_result_v2` 逻辑。仅确认 BREAKOUT（历史60/120日前高、放量、收盘位置）或 PULLBACK（上升结构、MA20回踩、收盘承接）两类结构。必须明确 entry_zone、max_entry_price、entry_trigger、invalidation_price、invalidation_rule、initial_risk_pct、exit_plan；待触发WAIT可以给条件区，不将其称作当天有效买点。
8. 完成发布前审计：fresh_company_research、working_set_frozen、pre_screen_coverage、company_research_coverage、structure_same_day、no_future_evidence、json_schema_valid 全部true；以及source-review、价格和状态一致。**无合法COMPLETE结果则报告失败，盘中标记“本轮趋势榜不可用”。**
9. 正式结果唯一写 research/trend_buy_formal_result.json，schema `trend_buy_result_v2`，包含明确run_id、trade_date、READY/WAIT/UNCERTAIN/DROP及审计。写前JSON序列化+反解析+完整Gate；GitHub提交后从main回读内容、SHA、run_id、名单逐项一致。
10. 仅19:00完整正式研究发布后，取已readback正式结果的真实 blob SHA，投影 scripts/trend_buy_handoff.py 的 `trend_buy_handoff_v2`，**唯一写 research/trend_buy_handoff.json**。HANDOFF只含READY+WAIT，严格采用`trend_buy_handoff_v2`字段契约，保留股票身份、交易计划和rank。写后READBACK比对。早7:00只是隔夜信息复核，不写handoff；人工明确要求完整收盘版且Gate全部通过时可更新。
11. 盘中唯一读取 research/intraday_market_snapshot.json，并确认其 source_stock_handoff_path 为 research/trend_buy_handoff.json、stock_handoff_kind=trend_buy_v2、schema/run_id/日期/名单完全一致后执行 skill/INTRADAY_MONITOR_CANONICAL.md。盘中不重新选股，不改入场价，不用历史“估值买点”补价，不自动下单。

## 3. 初始交易规则（继续运行中校准）

- BREAKOUT：当日收盘站稳前60/120日关键阻力（不含当日K线），当日/近5日量比确认且收盘在当日振幅位置≥55%；距MA20明显过大不追，跳空超max_entry_price取消买入。
- PULLBACK：已确认上升结构、higher_low、MA20附近实际触及、收盘重新站上MA20且高于前收盘并形成较强承接；仅碰到均线不是买点。
- 风控初值：入场区间上沿到失效价的价格距离上限6%；收盘距MA20>8%或chase=high时不追；已知合理上方阻力若不足1.5R暂缓；默认下一交易日最多1.2%执行价格容差。**这些均是试运行参数，后续根据假突破、最大回撤、换手、跳空、手续费实证调整。** 不知道上方阻力不能伪造涨幅目标。
- 价格区与失效价只是计划；实盘跳空、涨跌停、成交滑点可导致更大亏损；仓位按账户可承受错误成本决定。
- EXIT：①商业逻辑被证伪；②确认结构失效/突破失败；③市场/行业趋势衰退与个股转弱共振；④上涨后结构保护位上移及分批退出。盘中暂时跌破与收盘确认分开处理；持仓与空仓使用不同规则。不得因为价格反弹到成本价就机械清仓。

## 4. 状态与字段

- READY：**上游板块市场状态=趋势确认**、公司研究完成、入场结构已确认，下一交易日存在具风险边界的条件执行计划。不是即时无条件买入。
- WAIT：等待突破/回调/进一步确认/风险改善，`wait_reason` 只允许 WAIT_BREAKOUT / WAIT_PULLBACK / WAIT_CONFIRMATION / WAIT_RISK_REWARD。WAIT理由必须可理解；待触发区间不等于已经满足入场条件。
- UNCERTAIN：公司业务、K线/成交或日期口径缺口，不能给可信计划。
- DROP：公司业务关联反证、重大风险硬过滤，或明确结构损毁且不再可研究。
- EARLY_EVIDENCE 不能自动升级为商业化SUPPORTED，但可以在充分直接业务证据和额外经营风险复核后研究趋势买点。禁止把主营其他合同冒充主题商业兑现。

状态按行业、公司、来源时间、情景风险和价格证据完整覆盖。READY/WAIT须满足现行正式引擎的必填参数，handoff严格遵守`trend_buy_handoff_v2`字段契约。

### READY=0时：每板块一只“趋势萌芽期参考入场股”

**业务目标：研究领先于市场普遍确认，而不是等到板块趋势和个股突破双双确认才开始关注。** 对本轮上游每个已入选主题板块，只要该板块至少有一只经过研究的WAIT，**必须选一只**研究优先股票，标签 `EARLY_FOCUS_NOT_READY`。这只股允许处在板块“候选趋势”与个股“形态尚未标准确认”的阶段。没有合格WAIT则 `NO_QUALIFIED_WAIT`，绝不可从UNCERTAIN/DROP或预筛落选的股票补选，不能编造股票或价格。

**重点关注不是READY，不改变任何WAIT或盘中监控买卖信号。** 主榜仍有传统确认型READY，早期关注是**同一引擎的辅助输出**而不是第二套独立选股榜/自动交易引擎。即使股价接近MA20/MA60、存在量比变化、出现板块资金试探，也不能假称资金已流入、趋势已确认、必将上涨。

优先顺序不再以静态5%入场距离、是否有远期60日高点突破计划或PE最低来决定。改为**基于真实已完成日K的早期证据**：1日量比、5日持续量比、20日相对强弱、MA20斜率、当天收盘强度、近期更高低点；随后比较能否设计具备真实结构保护位的**条件性入场方案**、入场触发位置的可观察距离、明确经营/主题受益证据、预计价格风险，最后以原行业预筛分作同分参考。仅用日期一致、公司身份一致的原始价格结构和已核实公司业务材料；未知记未知。不得将“有远期突破价”误读为“近期可以考虑买”，也不得把接近MA60当作已经满足买点。

每只早期关注股必须写出：
1. 行业与公司代码、最近完整收盘价、行业当前状态、证据是哪些（量能、相对强弱、斜率、价格位置、公司业务关联），以及为何它比同板块其他WAIT优先。
2. **条件触发情景而非保证成交的买入建议**：观察重新站稳MA20/MA60、回踩承接或微结构反转。可列出真实均线的`reference_trigger_price`和附加量价/收盘确认，不是触及数值即直接下单。
3. 如果真实支撑/失效价与条件区能形成足够清晰的风险边界，输出 `reference_zone`、`invalidation_price`、初始价格风险；早期研究参考以8%为试验最大结构风险且**实际仓位仍须另按账户风险预算**。如果找不到可信近端止损，仍提供该板块的一只优先股票，但`reference_zone=null`，明确标记“仅观察、尚不具备可执行买入区”，禁止假造止损价。
4. 从EARLY_FOCUS进入READY还缺的板块确认、价格确认、业务证据、跳空滑点/仓位等障碍及使研究被推翻的条件。早期尝试若用户自己选择参与，必须单独承担更高假突破/频繁止损可能性；系统不得推送为已确认交易信号。

正常READY>0时照常优先显示所有READY；只要READY=0即每板块输出一只EARLY_FOCUS或无合格WAIT，不因缺乏标准READY信号而放弃趋势萌芽期研究。每次运行需重算，禁止沿用前一天的参考触发价。夜间完整正式榜若发布失败，不将昨日价格冒充今日买入机会。盘中不因EARLY_FOCUS升级自动入场。

## 5. 唯一版本与异常原则

每日“A股趋势买点榜”按北京时间07:00、19:00执行，并严格校验官方交易日；上游板块趋势榜按06:40、18:40提供行业交接，盘中监控按既定时段消费已发布的正式快照。

没有有效正式结果时，报告 `MORNING_HANDOFF_UNAVAILABLE` 或 `NO_VALID_TREND_BUY_HANDOFF`，不生成没有数据依据的交易判断。

每次失败记录具体阶段、工具、readback/commit与真实错误；权限或安全拒绝不得换工具规避。失败不覆盖最后一份时间适用的COMPLETE正式结果，不以过期数据冒充新日期。完整审计通过后才称PERSISTED。

公司筛选使用 `PRE_SCREEN_RESEARCH_SCOPE_OVERRIDE.md`，行业路由使用 `TREND_HANDOFF_ROUTING_OVERRIDE.md`，交易计划与发布以本文件和 `scripts/trend_buy_engine.py` 为准。

# A股盘中交易执行监测｜唯一执行规则（7日监测指标）

时间统一按 Asia/Shanghai；仓库 xwan008/a-market-data，分支 main。保持现有盘中执行监测、板块/ETF 与 READY/WAIT 个股执行判断、状态持久化业务边界；只统一**板块与个股的盘中短周期历史收益指标为七个完整交易日**。禁止改写或重算上游板块趋势榜、低风险买点榜、研究 handoff、估值或选股。

## 1. 交易日、数据与范围 Gate（最高优先级）

每轮先取得当前北京时间并依据上交所/深交所官方交易日历或官方休市公告确认 today 为 A 股正式交易日，不得仅根据星期判断。非正式交易日或无法可靠确认时立即结束：不读取旧快照冒充今日、不初始化或更新状态、不写 GitHub、不生成买卖动作。

唯一行情及历史事实输入：main 上的 research/intraday_market_snapshot.json；当天执行记录唯一输入：research/intraday_monitor_state.json。本规则文件只提供执行规范，不是行情源。Web 仅用于官方交易日确认；禁止额外搜索行情或直接读取 history_shards / 其他研究数据来补充快照中的事实。只监测当天首次有效快照所冻结的 trends 和正式 READY/WAIT 个股。

快照必须同时满足：result_kind=a_share_intraday_market_snapshot；snapshot.trade_date=today；captured_at 距真实扫描时间 0–15 分钟；validation.status=passed；validation.quote_coverage>=0.90；manifest_errors=[]；source_trend_trade_date/source_low_risk_trade_date 均非空且相等，source_handoff_trade_date_consistent 若提供必须为 true。低风险 handoff 的覆盖率、来源版本与校验须与快照一致；不能以外部价格弥补缺失。任何核心 Gate 失败则报告 SNAPSHOT_INVALID / HANDOFF_SOURCE_MISMATCH / DATA_INSUFFICIENT，不产生本轮动作或状态迁移。

## 2. 七个完整交易日的历史数据约定

- 板块读取 snapshot.trends[*].history_context.seven_day：window_sessions=7（八个有效收盘价、七个收益区间）、median_constituent_return_pct（当前冻结成分股七日涨幅的中位数）、positive_constituent_ratio、sample_count、target_count、coverage_ratio、status。它不是板块指数涨幅，也不是指数超额收益。仅 status=available 且必要覆盖与日期自洽时作为充分历史佐证；partial 必须显式标注样本局限；unavailable 不推断。
- 个股读取 snapshot.low_risk_stocks[*].seven_day：window_sessions=7、status、source_trade_date、observation_count、close_change_7d_pct；只有 available、8 个有效收盘点且 source_trade_date 与正式历史基准一致时，才报告有效七日涨幅。历史技术结构仍参考 snapshot.low_risk_stocks[*].history_context 的 history_confidence、trend_state、break_state、latest_high、latest_low、invalidation 等；只有 history_context_status=available、confidence 为 high/medium 且字段自洽时作有效增强证据。
- 不得再使用、推断或把旧 close_change_5d_pct、five_day 当七日数据。七日历史仅提供跨日背景，不能单独触发买入、减仓、退出或当日结构动量变化；必须结合当前行情、板块广度、中位数、个股相对行业表现、上游趋势和同日变化。
- 可参考 history_context.previous_trade_day、low_risk_stocks[*].previous_trade_day_monitor，但前者是**上一个正式数据日最后一次已成功持久化的盘中扫描**，不是官方收盘状态或行情；板块只有 same_industry_codes=true 才可直接比较成分口径。历史缺失绝不阻断有效实时扫描，不凭空补历史。

## 3. 新交易日与同日 previous_*

state 不存在或不是今天时，新建 monitor_date=trade_date=snapshot.trade_date，清空重建当天 industry_history/stock_history；以今天第一份有效快照冻结趋势名称、rank、行业代码、READY/WAIT 股票身份与正式顺序及 handoff 来源日。首轮所有 previous_*=null，不继承上一个自然日或交易日 intraday state。只有同一 trade_date **更早、有效、已经成功提交且 READBACK 验证**的上一轮扫描，才能赋给 previous_*。当天后续快照中来源日、冻结趋势与 READY/WAIT 身份/rank/顺序必须与首轮完全一致，否则 SNAPSHOT_UNIVERSE_MISMATCH，不做状态迁移。state 完整 JSON 无法读取、日期/冻结范围/上一轮有效性无法验证时报告 STATE_READ_INVALID / DATA_INSUFFICIENT，不拼接猜测或盲目覆盖。

## 4. 板块/ETF 执行（不得重新研究上游趋势）

联合 snapshot.trends 的上游 trend_state / market_state、有效七日板块历史、实时 quoted_count/coverage_ratio、up_count/down_count/up_ratio、median_change_pct、max/min_change_pct、所有成分 change_pct，以及同日上一轮有效扫描变化；不得拿单一龙头代替全板块，也不得逆向修改上游结论。

板块 current_state 仅 正常/分歧/修复/衰退预警：
- 正常：广度、中位数及扩散没有同步实质弱化。
- 分歧：相对同日上一轮或首轮横截面，至少两类结构指标同步恶化。
- 修复：上一轮分歧/预警后至少两类指标改善且不依赖单一成分。
- 衰退预警：同日已分歧后继续恶化；或首轮上游 market_state 已高潮/衰退/失效且当前横截面至少两类同步弱化。
绝不因上一交易日最后一次盘中状态直接将今天首轮判为衰退。
structure_momentum 仅 增强/稳定/减弱；同日对比至少两类改善才增强，两类恶化才减弱，否则稳定；首轮 previous_structure_momentum=null、structure_momentum=稳定，七日涨跌不冒充同日动量。

ETF 空仓动作为 可跟随/关注回踩/等待/不追涨/暂停买入；有效上游+当下正常/修复+动量增强或广度明显健康才可跟随；趋势有效但缺少承接则关注回踩或等待，明显加速/集中不追涨，上游高潮/衰退/失效或分歧持续且减弱则暂停。首轮除充分共振外不激进。ETF 持仓动作为 继续持有/持有观察/减仓观察/减仓/退出；上游有效且正常/修复、动量稳定/增强可继续持有，一般分歧或短暂减弱持有观察；上游衰退迹象与当下同步弱化或同日持续分歧且两类进一步恶化可减仓观察；上游高潮/衰退与实时恶化共振可减仓；上游失效且结构持续明显弱化、失效确认才退出。不凭单次分歧退出；首轮若上游已明确衰退/失效且今天确认弱势，可按原规则触发。没有明确 ETF 代码不得猜测。

## 5. READY/WAIT 个股盘中执行

仅监测今天正式冻结的 READY/WAIT，禁止重选股或重估值。trend_in_current_handoff=false 时空仓至少暂停买入、持仓至少持有观察，不能仅因此退出。

综合四组证据：①历史七日涨幅及有效历史结构 trend_state/break_state/latest_high/latest_low/invalidation；②当前 price/change_pct/industry_median_change_pct/relative_to_industry_pct；③实时行业动量与上游趋势；④同日持久化 previous_*。relative_strength 仅 增强/稳定/减弱，根据同日行业相对优势扩张/持平/收窄，首轮 previous_relative_strength=null、默认稳定，不把七日历史冒充同日增减。price_behavior 仅 强化/承接/震荡/加速/转弱/结构破坏：涨幅和相对优势同日持续改善而未过度加速为强化；行业弱而个股相对强且历史结构未破为承接；变化不大且历史有效为震荡；短时优势快速扩大为加速；同日明显减弱或历史弱化背景下再度走弱为转弱。

结构破坏要求多证据共振：历史已 bearish/break 且现价未修复、弱于行业且行业恶化；或现价明确跌破历史 invalidation 未修复且行业分歧/衰退；或历史 intact/bullish 下同日多轮持续转弱、跌破 latest_low/invalidation 且行业持续恶化。无历史时首轮默认震荡、不凭空判结构破坏；已有明确历史破坏并获今日价格和行业确认时首轮可判破坏。

个股空仓动作仅 可跟随/关注回踩/等待/不追涨/暂停买入。历史健康+行业正常/修复+个股增强且强化/承接可跟随；健康但待承接关注回踩；历史 transition/break、行业预警或个股明显减弱/转弱暂停；有效趋势但加速或远离合理区不追涨；其余等待。买入区间用于安全边际/追高风险提示，非买入硬 Gate。
个股持仓动作仅 继续持有/持有观察/减仓观察/减仓/退出。历史健康+行业一般分歧+个股稳定/增强且未破坏可持有/观察；历史 transition/弱化+今天减弱/转弱而行业尚未共振可观察或减仓观察；行业跨日衰退且今天弱化、个股历史与今天转弱共振可减仓；行业衰退/失效持续恶化且个股历史 break/invalidation 获今天价格确认才退出。上游不能盘中核实的订单或业绩失效不得用价格代替；卖出确认比买入严格，优先行业和个股共振。区分不追涨与卖出、持有与新仓买入。

## 6. 唯一状态持久化、校验和错误

只允许写 main 上 research/intraday_monitor_state.json。State 包含 schema_version、result_kind=a_share_intraday_monitor_state、execution_schema_version=2、trade_date/monitor_date、last_scan_at、snapshot_at、冻结 handoff 日期和全部身份/rank、industry_history/stock_history。每条行业记录保存 trend_name、上游状态、previous_state/current_state、previous_structure_momentum/structure_momentum、广度/涨跌/覆盖/中位数、previous_entry_action/entry_action、previous_holding_action/holding_action、reason 和 data_quality；个股每条保存完整身份与 rank、价格/相对行业、历史可用性和有效七日摘要、previous_relative_strength/relative_strength、previous_price_behavior/price_behavior、前后操作、买入区间关系、handoff 标志、reason、data_quality。

先构造完整对象并用可执行环境实际 JSON 序列化和 JSON.parse 同一个待提交文本，核验字段、日期、全部冻结身份和行业/股票覆盖、枚举值及 previous_* 仅来自同日更早已落库扫描。不接受省略、截断或目测检查。无法校验则 PREWRITE_JSON_INVALID，最多在同一有效快照和已核实状态下完整重建一次，仍失败则 STATE_WRITE_FAILED，绝不将失败轮次纳入历史。

写入前重新读取 main 目标文件最新全文及 blob SHA，只在实际写工具返回新 commit_sha、content_sha 后立即从 main READBACK 完整 JSON 和 SHA，比较日期、last_scan_at、来源日、冻结身份和排序、行业/股票各轮完整覆盖、必需字段及内容一致性。全部通过才报告 STATE_PERSISTED 且允许作为下一轮 previous_*。失败则 STATE_WRITE_FAILED/READBACK_JSON_INVALID/READBACK_MISMATCH，不冒称持久化或盲目二次覆盖。SHA_CONFLICT 必须重读、重做前置验证后最多重试一次。记录 READ_SOURCE、PREPARE_PAYLOAD、PREWRITE_JSON_PARSE、PREWRITE_SCHEMA_VERIFY、WRITE_REQUEST、WRITE_RESPONSE、READBACK、READBACK_JSON_PARSE、VERIFY 阶段及 attempt_id、日期、目标、工具、旧/新 SHA 和实际可见的脱敏错误；不可见 HTTP status/error.code/request_id 标 unavailable，不推测 403/409。

明确的 PRECHECK_BLOCKED（安全预检）不可将内容视为已落库，不得更换通道、拆分/编码/删减 payload 绕过；若执行环境许可，按既有受控规则延迟 30–60 秒，重新获取相同路径当前 SHA、验证相同语义的完整文本，以原工具最多原样重试一次；第二次仍被阻断立即停止并报告 PRECHECK_BLOCKED_REPEATED 和两次实际证据。其他权限/安全拒绝或审批要求须停止并如实报告。

## 7. 输出顺序与原则

标题“A股盘中交易执行监测｜北京时间 <scan time>”。先报告 captured_at、报价覆盖、正式交易日/Gate、板块七日历史及个股七日历史的可用性、持久化结果；Gate 未通过时不输出当轮交易动作。通过后按冻结顺序完整展示所有板块/ETF：方向、上游趋势、七日板块统计（真实中位数、上涨比例、样本覆盖）、板块 previous→current、动量 previous→current、空仓/持仓动作及具体证据。再按正式 rank 展示所有 READY/WAIT 个股：历史七日收益及技术结构、现价、行业相对表现、相对强弱、价格行为、空仓/持仓动作及依据。无有效历史则明示，不漏股，不虚构。最后只补重大动作变化；无强信号时如实报告。永不反向修改上游趋势榜、低风险榜或正式 handoff。

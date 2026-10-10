# A股盘中交易执行监测｜唯一执行规则（7日监测指标）

时间统一按 Asia/Shanghai；仓库 xwan008/a-market-data，分支 main。保持现有盘中执行监测、板块/ETF 与 READY/WAIT 个股执行判断、状态持久化业务边界；短周期历史收益统一为**七个完整交易日**，并将盘中分歧与跨日趋势衰退的证据分层。禁止改写或重算上游板块趋势榜、趋势买点榜、研究 handoff、估值或选股。

## 1. 交易日、数据与范围 Gate（最高优先级）

每轮先取得当前北京时间并依据上交所/深交所官方交易日历或官方休市公告确认 today 为 A 股正式交易日，不得仅根据星期判断。非正式交易日或无法可靠确认时立即结束：不读取旧快照冒充今日、不初始化或更新状态、不写 GitHub、不生成买卖动作。

唯一**行情及历史事实**输入：main 上的 research/intraday_market_snapshot.json；当天执行记录唯一输入：research/intraday_monitor_state.json。Airtable 仅作为附加的**用户交易记录/持仓上下文**，严格按第5A节读取，不是行情、正式收盘价、趋势研究或股票池来源。本规则文件只提供执行规范，不是行情源。Web 仅用于官方交易日确认；禁止额外搜索行情或直接读取 history_shards / 其他研究数据来补充快照中的事实。只监测当天首次有效快照所冻结的 trends 和正式 READY/WAIT 个股；Airtable 不得扩张冻结交易监测股票池。

快照必须同时满足：result_kind=a_share_intraday_market_snapshot；snapshot.trade_date=today；captured_at 距真实扫描时间 0–15 分钟；validation.status=passed；validation.quote_coverage>=0.90；manifest_errors=[]；source_trend_trade_date/source_trend_buy_trade_date 均非空且相等，source_handoff_trade_date_consistent 若提供必须为 true。趋势买点 handoff 的覆盖率、来源版本与校验须与快照一致；不能以外部价格弥补缺失。任何核心 Gate 失败则报告 SNAPSHOT_INVALID / HANDOFF_SOURCE_MISMATCH / DATA_INSUFFICIENT，不产生本轮动作或状态迁移。

## 2. 七个完整交易日的历史数据约定

- 板块读取 snapshot.trends[*].history_context.seven_day：window_sessions=7（八个有效收盘价、七个收益区间）、median_constituent_return_pct（当前冻结成分股七日涨幅的中位数）、positive_constituent_ratio、sample_count、target_count、coverage_ratio、status。它不是板块指数涨幅，也不是指数超额收益。仅 status=available 且必要覆盖与日期自洽时作为充分历史佐证；partial 必须显式标注样本局限；unavailable 不推断。
- 个股读取 snapshot.trend_buy_stocks[*].seven_day：window_sessions=7、status、source_trade_date、observation_count、close_change_7d_pct；只有 available、8 个有效收盘点且 source_trade_date 与正式历史基准一致时，才报告有效七日涨幅。历史技术结构仍参考 snapshot.trend_buy_stocks[*].history_context 的 history_confidence、trend_state、break_state、latest_high、latest_low、invalidation 等；只有 history_context_status=available、confidence 为 high/medium 且字段自洽时作有效增强证据。
- 不得再使用、推断或把旧 close_change_5d_pct、five_day 当七日数据。七日统计是截至指定历史基准日的**累计七日截面**，不包含七天逐日板块路径；七日中位数为负、上涨比例低，不等于「最近连续七天恶化」，也不能直接证明今日盘中回落即为趋势衰退。七日历史不得单独触发买卖、状态升级或当日动量变化，必须结合实时横截面与可核实的跨日信息。
- 跨日参照仅可来自 snapshot.trends[*].history_context.previous_trade_day 与 trend_buy_stocks[*].previous_trade_day_monitor 等快照自带的已核实字段；其中 previous_trade_day 是**上一个正式数据日最后一次已成功持久化的盘中扫描**，不是官方收盘价或正式收盘确认。行业跨日可比需同时满足：trade_date 明确早于 today 且为快照声明的前一个有效数据日，same_industry_codes=true，双方报价覆盖率 >=90%，历史 data_quality=READY，指标/成分口径一致；否则标「跨日证据不可比/不足」，不得强行判断跨日恶化。即使可比，也须注明其为两次盘中截面比较，不能称为逐日连续趋势或官方收盘数据。历史不足不阻断有效的当天监测，但限制趋势衰退升级的证据等级。

## 3. 新交易日与同日 previous_*

state 不存在或不是今天时，新建 monitor_date=trade_date=snapshot.trade_date，清空重建当天 industry_history/stock_history；以今天第一份有效快照冻结趋势名称、rank、行业代码、READY/WAIT 股票身份与正式顺序及 handoff 来源日。首轮所有 previous_*=null，不继承上一个自然日或交易日 intraday state。只有同一 trade_date **更早、有效、已经成功提交且 READBACK 验证**的上一轮扫描，才能赋给 previous_*。当天后续快照中来源日、冻结趋势与 READY/WAIT 身份/rank/顺序必须与首轮完全一致，否则 SNAPSHOT_UNIVERSE_MISMATCH，不做状态迁移。state 完整 JSON 无法读取、日期/冻结范围/上一轮有效性无法验证时报告 STATE_READ_INVALID / DATA_INSUFFICIENT，不拼接猜测或盲目覆盖。

## 4. 板块/ETF 执行（不得重新研究上游趋势）

联合 snapshot.trends 的上游 trend_state / market_state、有效七日板块历史、实时 quoted_count/coverage_ratio、up_count/down_count/up_ratio、median_change_pct、max/min_change_pct、所有成分 change_pct，以及同日上一轮有效扫描变化；不得拿单一龙头代替全板块，也不得逆向修改上游结论。

板块 current_state 仍仅 正常/分歧/修复/衰退预警，不扩展枚举；必须把「盘中风险动作」与「跨日趋势状态」分开判断：
- 正常：广度、中位数及扩散没有同步实质弱化，且不存在待延续的未修复分歧。
- 分歧：相对同日更早的有效扫描，广度（up_ratio/up_count 为同一类，不能重复计数）与中位数（median_change_pct）等至少两类实质恶化；连续多轮恶化但未满足下述升级门槛时仍为「分歧」，reason 明写「分歧持续、盘中风险升高」，不得仅因「前轮已分歧＋本轮再恶化」自动升级。
- 修复：此前分歧/预警后，至少两类结构指标在同日有效扫描中改善，且改善具有成分扩散性、不依赖单一涨幅极值；未改善或仍在走弱不得只因调整新规则而称「修复」。
- 衰退预警：除当前确有广度与中位数等至少两类实质弱化外，还必须满足**以下任一独立确认路径**；不可用同日多轮恶化替代独立确认：
  A. 上游快照 market_state 已明确为「衰退」或「失效」，且实时横截面至少两类同步弱化；「高潮」或「趋势确认」本身均不是衰退的证明。已有明确上游失效且当前恶化可在首轮预警，但不能把旧日 intraday_state 直接继承为今日状态。
  B. snapshot 中的 previous_trade_day 跨日可比性满足第2节所有约束，且本轮 up_ratio **低于**前交易日有效扫描、median_change_pct **低于**前交易日有效扫描，当前上涨比例已不足50%且成分涨幅中位数转负，并且今天盘中出现至少两类进一步实质弱化。两个跨日比较项须分别列数值，不能拿七日累计统计代替。
  C. 当 previous_trade_day 不可用或不可比时，snapshot 的有效七日板块历史 status=available、window_sessions=7、coverage_ratio>=90%、日期/样本自洽，七日涨幅中位数为负且七日正收益成分比例低于50%，同时**今天**上涨比例低于50%、当日涨幅中位数为负、同日多轮至少两类指标持续恶化，才可作为较低置信度的衰退预警；明示没有正式跨日逐日走势证据，绝不由七日负收益单独触发。
- 证据冲突优先处理：若可比的 previous_trade_day 证明本轮上涨占比和涨幅中位数均不低于上次有效跨日截面，禁止仅凭七日历史为负或今日盘中回落使用路径 B/C 升级；上游已明确衰退/失效并实时确认者仍可走路径 A。若存在快照已明确、可核验的板块关键结构位失效证据，也只能在其自身规则确证且多成分弱化时提出越级风险；现有快照缺少板块关键结构位字段，不得凭空制造失效点或越级确认。
- 证据不足或互相矛盾时守住「分歧/分歧持续」，把疑点写在 reason；衰退预警是风险前瞻标签，**不是已经确认趋势失效**，也不自动意味着退出。分歧、修复、衰退预警均不得逆向改写上游 trend_state/market_state。
- 当日此前按旧规则标为「衰退预警」，而当前依新门槛不再满足时，可调整为「分歧」并在 reason 写明「风险标签按新门槛重新分层、盘中分歧尚未修复」，不得谎称价格结构已修复；previous_state 仍取同日实际已持久化历史值。
structure_momentum 仅 增强/稳定/减弱；同日对比至少两类改善才增强，两类恶化才减弱，否则稳定；首轮 previous_structure_momentum=null、structure_momentum=稳定，七日涨跌不冒充同日动量。

ETF 空仓动作为 可跟随/关注回踩/等待/不追涨/暂停买入；有效上游+当下正常/修复+动量增强或广度明显健康才可跟随；趋势有效但缺少承接则关注回踩或等待，明显加速/集中不追涨，**分歧持续且动量减弱时即使尚未构成衰退预警，也可暂停买入**。上游高潮/衰退/失效且当下恶化亦可暂停；首轮除充分共振外不激进。
ETF 持仓动作为 继续持有/持有观察/减仓观察/减仓/退出；上游有效且正常/修复、动量稳定/增强可继续持有，普通分歧或单日持续分歧但跨日证据不足原则上持有观察；若同日持续分歧并出现进一步两类实质恶化，可在已有个股/ETF 自身弱化佐证时升级「减仓观察」，但该标签**不等于已执行减仓**，不能仅由板块状态名称自动卖出。确认的上游衰退迹象与跨日/当下弱化共振可减仓观察；上游高潮/衰退与实时显著恶化共振且价格结构证据充分才可减仓；上游失效且结构持续明显弱化、失效确认才退出。不凭单次分歧、七日累计收益为负或单一标签退出；首轮上游已明确衰退/失效且今天确认弱势，可按原规则触发。没有明确 ETF 代码不得猜测。

## 5. READY/WAIT 个股盘中执行｜仅趋势买点V2

个股唯一输入为 snapshot.trend_buy_stocks[*]，冻结身份只来自同日 research/trend_buy_handoff.json；不再允许任何旧低PE榜合理价值区、低风险折扣价和旧WAIT_PRICE/WAIT_MARGIN作为买卖依据。今天正式冻结的全部READY/WAIT均要展示，严禁重选股、重研究或重估值。

空仓动作：只有已发布READY并且 entry_trigger在当前行情中仍有效、现价位于entry_zone且不超过max_entry_price、板块/个股相对强弱与价格行为没有破坏证据时，才可提出“条件可跟随”；WAIT一律“等待确认/关注回调”，不得因进入等待区间就说可直接买入。超max_entry_price、跳空超标或价格剧烈加速一律“不追价”；业务与量价证据无效则“暂停买入”。空仓动作合法枚举仍沿用 可跟随/关注回踩/等待/不追涨/暂停买入。

持仓动作：按快照中已冻结的invalidation_price、invalidation_rule、exit_plan及有效历史结构判断，不把“盘中短暂跌破”误作“收盘确认失效”。历史结构破坏、板块趋势持续衰退与今日相对优势持续减弱可增强减仓/退出判断；缺少共振先持有观察。突发事件和跳空触发即时风险复核，但止损参考价不能保证成交。持仓动作沿用 继续持有/持有观察/减仓观察/减仓/退出，卖出证据门槛高于空仓入场。trend_in_current_handoff=false时空仓暂停买入、持仓至少持有观察，不自动清仓。

仍须对本轮每只股票区分七日历史、当日盘中变化和上一完整交易日盘中截面；相对行业表现只使用本轮冻结快照；高价区与企业估值没有等号。

## 5A. Airtable 实际持仓优先关注（轻量、只读，不扩行情池）

本节仅增加盘中**持仓上下文与展示优先级**，绝不增加采集频率、行情源、GitHub 数据写入或新的监测定时任务。保留原有时间表、快照生成与行情 Gate、冻结范围、现有状态枚举、原有 READY/WAIT 全量覆盖和唯一 intraday_monitor_state.json 写入/回读链；不更改上游任何研究结果。持仓观察**不构成自动交易**。

**连接与读取：**仅在正常完成第1节行情/日期 Gate 后，使用已连接的 Airtable 只读接口读取 base「交易复盘日志」（baseId=apphDsZysIUy8JciR）中的「交易记录」（tableId=tblEvj2Gc3QlLanpK）。取「股票代码」「交易标的」「操作类型」「价格（元）」「实际成交股数」「金额（元）」「交易日期」「记录日期」「失效条件」「复盘备注」，按接口 nextCursor 遍历至结束，不把首批分页误认为全部。调用不可用、权限失败、分页中断或字段缺失时标记 PORTFOLIO_CONTEXT_UNAVAILABLE/INCOMPLETE，仍按原规则执行全量板块与 READY/WAIT 监测；**绝不能把读取失败解释为没有持仓、没有风险，或通过外部市场数据兜底**。不写 Airtable、不过量重试。

**持仓核验与汇总：**
- 只按可核实的六位证券代码准确匹配；原始买入/卖出/清仓记录均须核对操作类型与成交股数，不能把记录日期冒充成交日期，不能把仓位比例、预估金额或备注当作已成交股数。先按交易日期与可核实顺序重建交易；若卖出先后顺序不明、重要成交数量缺失、标签不认识或记录冲突，标记该代码「持仓数量/成本待核验」，不得虚构净持仓。
- 对可核实的首仓/买入/加仓增加实际股数，对减仓/卖出扣减实际股数；清仓仅在实际已成交数量可核实时清零。净持仓 >0 才列为「Airtable 登记持仓」；=0 不列持仓；不推断未来成交或自动修改记录。买入成本按成交股数×单价核算，期间有卖出时仅在交易顺序可靠前提下以移动加权平均法估算剩余成本；缺失必要价格时只报告有效数量，不造成本；手续费、税费及滑点另注明未计。Airtable 数据仅是用户记录，不保证与券商实际持仓完全一致。
- 优先解析每只持仓的「失效条件」为**用户已记录的观察计划**。同一股票不同记录条件如不一致、过期、临时待复核或仅为文本模糊描述，则明示「待复核」并保留来源记录，不自行发明或上移止损价，不把买入成本当失效线。

**与盘中快照的匹配：**只用股票代码把 Airtable 的净持仓匹配到**当天冻结的** snapshot.trend_buy_stocks 正式 READY/WAIT 股票身份，命中才结合本轮有效行情、7日有效历史、原规则的相对行业表现与同日变化输出重点分析，并解释原有的 holding_action（持仓动作）而非将 entry_action（空仓动作）冒充持仓建议。不能因为用户持仓修改当前板块 current_state、个股结构判断、原有正式 rank 或买卖动作触发阈值。未命中冻结股票池的已登记持仓，只可提示「现有快照未覆盖，本轮无可靠盘中价格/结构信号」，不新增股票、不调用其他行情接口、不写入 state 的冻结身份。记录为空且完整读取成功，明确「Airtable 未发现可核实的在持股票」；读取失败不得做此结论。

**风控语义：**可计算当前**有效盘中报价**相对登记成本的浮动差额（注明不含费用），并检查已记录的**盘中预警条件**；用户约定「日线收盘价低于某价才失效」时，盘中低于该价**只能提示接近/盘中触及待收盘核验**，不是已确认收盘跌破、也不得自动减仓或退出。快照只有盘中报价时，绝不把该报价/上一交易日盘中扫描称为正式收盘价。即使价格触线也不单靠成本盈亏、单次波动或板块预警直接下卖出结论；分开说明「触发了什么观察条件」「哪些确认条件仍缺失」「原有模型的持仓动作」。

**输出与落库边界：**在原有板块完整输出之后、正式 READY/WAIT 逐股输出之前，增加简短「Airtable 持仓重点关注」：是否读取成功、记录核对时点与核验状态、持仓代码/名称、有效股数和估算成本、当前快照报价及其时间、关键观察/收盘失效条件、对应原模型 holding_action、证据和待确认项；按风险程度优先，但不改变正式股票排名及后续原始榜单展示。随后仍按原正式 rank 完整输出所有 READY/WAIT，不漏股、不重复新建 signal。**持仓信息为每轮临时展示上下文，不增加 state schema 字段，不持久化 Airtable 原始记录至 GitHub**。如行情 Gate 未通过，禁止借 Airtable 数据输出任何盘中买卖动作。

## 6. 唯一状态持久化、校验和错误

只允许写 main 上 research/intraday_monitor_state.json。State 包含 schema_version、result_kind=a_share_intraday_monitor_state、execution_schema_version=2、trade_date/monitor_date、last_scan_at、snapshot_at、冻结 handoff 日期和全部身份/rank、industry_history/stock_history。每条行业记录保存 trend_name、上游状态、previous_state/current_state、previous_structure_momentum/structure_momentum、广度/涨跌/覆盖/中位数、previous_entry_action/entry_action、previous_holding_action/holding_action、reason 和 data_quality；个股每条保存完整身份与 rank、价格/相对行业、历史可用性和有效七日摘要、previous_relative_strength/relative_strength、previous_price_behavior/price_behavior、前后操作、买入区间关系、handoff 标志、reason、data_quality。

先构造完整对象并用可执行环境实际 JSON 序列化和 JSON.parse 同一个待提交文本，核验字段、日期、全部冻结身份和行业/股票覆盖、枚举值及 previous_* 仅来自同日更早已落库扫描。不接受省略、截断或目测检查。无法校验则 PREWRITE_JSON_INVALID，最多在同一有效快照和已核实状态下完整重建一次，仍失败则 STATE_WRITE_FAILED，绝不将失败轮次纳入历史。

写入前重新读取 main 目标文件最新全文及 blob SHA，只在实际写工具返回新 commit_sha、content_sha 后立即从 main READBACK 完整 JSON 和 SHA，比较日期、last_scan_at、来源日、冻结身份和排序、行业/股票各轮完整覆盖、必需字段及内容一致性。全部通过才报告 STATE_PERSISTED 且允许作为下一轮 previous_*。失败则 STATE_WRITE_FAILED/READBACK_JSON_INVALID/READBACK_MISMATCH，不冒称持久化或盲目二次覆盖。SHA_CONFLICT 必须重读、重做前置验证后最多重试一次。记录 READ_SOURCE、PREPARE_PAYLOAD、PREWRITE_JSON_PARSE、PREWRITE_SCHEMA_VERIFY、WRITE_REQUEST、WRITE_RESPONSE、READBACK、READBACK_JSON_PARSE、VERIFY 阶段及 attempt_id、日期、目标、工具、旧/新 SHA 和实际可见的脱敏错误；不可见 HTTP status/error.code/request_id 标 unavailable，不推测 403/409。

明确的 PRECHECK_BLOCKED（安全预检）不可将内容视为已落库，不得更换通道、拆分/编码/删减 payload 绕过；若执行环境许可，按既有受控规则延迟 30–60 秒，重新获取相同路径当前 SHA、验证相同语义的完整文本，以原工具最多原样重试一次；第二次仍被阻断立即停止并报告 PRECHECK_BLOCKED_REPEATED 和两次实际证据。其他权限/安全拒绝或审批要求须停止并如实报告。

## 7. 输出顺序与原则

标题“A股盘中交易执行监测｜北京时间 <scan time>”。先报告 captured_at、报价覆盖、正式交易日/Gate、板块七日历史及个股七日历史的可用性、持久化结果；Gate 未通过时不输出当轮交易动作。通过后按冻结顺序完整展示所有板块/ETF：方向、上游趋势、七日板块统计（真实中位数、上涨比例、样本覆盖）、板块 previous→current、动量 previous→current、空仓/持仓动作及具体证据。每个板块须分开展示「今日盘中变化」「七日累计历史」「可比的前交易日盘中截面」及「升级门槛是否满足」，列出参与判断的广度和中位数；跨日不可比要明确写原因，区分「分歧持续」与「衰退预警」，也须区分「减仓观察」与真正减仓。再按第5A节展示 Airtable 持仓重点关注（只使用冻结股票池内行情；缺数据须明示），最后按正式 rank 展示所有 READY/WAIT 个股：历史七日收益及技术结构、现价、行业相对表现、相对强弱、价格行为、空仓/持仓动作及依据。无有效历史则明示，不漏股，不虚构。最后只补重大动作变化；无强信号时如实报告。永不反向修改上游趋势榜、趋势买点榜或正式 handoff。

## 8. 唯一版本断言

在任何本轮交易动作或状态持久化之前，必须核验 snapshot.schema_version=2、stock_handoff_kind=trend_buy_v2、source_stock_handoff_path=research/trend_buy_handoff.json、source_trend_buy_handoff_schema_version=trend_buy_handoff_v2，以及快照冻结名单、trade_date、source_run_id和validations全部匹配。若本轮新版有效基线缺失或快照仍是旧格式，报NO_VALID_TREND_BUY_HANDOFF或SNAPSHOT_INVALID；**绝不运行旧版本，也绝不继承旧版本同日previous_*。** 有效新版首轮 previous_*=null。

个股具体条件只以 trend_buy_stocks[*].trend_entry_plan 的setup_type、entry_zone、entry_trigger、max_entry_price、invalidation_price、invalidation_rule、initial_risk_pct、exit_plan为准。禁止参考旧版低估值区间或在盘中重新画出买点。拒绝从旧研究结果和已退役handoff恢复。继续遵守前述板块/ETF证据、七日历史、持仓只读、日期Gate、写前完整JSON解析和GitHub commit+READBACK规则。

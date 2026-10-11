# A股盘中交易执行监测｜唯一执行规则（7日监测指标）

时间统一按 Asia/Shanghai；仓库 xwan008/a-market-data，分支 main。保持现有盘中时段、板块/ETF、READY/WAIT 全量机会观察及状态持久化业务边界；实际持仓独立优先管理；短周期历史收益统一为**七个完整交易日**，并将盘中分歧与跨日趋势衰退的证据分层。禁止改写或重算上游板块趋势榜、趋势买点榜、研究 handoff、估值或选股。

## 1. 交易日、数据与范围 Gate（最高优先级）

每轮先取得当前北京时间并依据上交所/深交所官方交易日历或官方休市公告确认 today 为 A 股正式交易日，不得仅根据星期判断。非正式交易日或无法可靠确认时立即结束：不读取旧快照冒充今日、不初始化或更新状态、不写 GitHub、不生成买卖动作。

唯一行情输入为 main 的 research/intraday_market_snapshot.json，以及仅供**Airtable 核验真实持仓**使用且经过本轮快照 SHA256 索引校验的 research/intraday_quote_shards/XX.json；分片来自同一次全市场公开报价采集，绝不包含任何个人持仓。当天执行状态输入为 research/intraday_monitor_state.json。Airtable 是实际持仓身份和预设交易计划的只读来源，不是行情或正式收盘价来源。Web 仅用于官方交易日确认，禁止盘中临时搜索行情或其他研究文件补数据。冻结的 trends 和 READY/WAIT 名单不得因实际持仓扩张；实际持仓另开独立管理分支（不进入排名或冻结股票池）。

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
- 当日此前标为「衰退预警」，而本轮重新核验后不再满足时，可调整为「分歧」并在 reason 写明「风险标签按新门槛重新分层、盘中分歧尚未修复」，不得谎称价格结构已修复；previous_state 仍取同日实际已持久化历史值。
structure_momentum 仅 增强/稳定/减弱；同日对比至少两类改善才增强，两类恶化才减弱，否则稳定；首轮 previous_structure_momentum=null、structure_momentum=稳定，七日涨跌不冒充同日动量。

ETF 空仓动作为 可跟随/关注回踩/等待/不追涨/暂停买入；有效上游+当下正常/修复+动量增强或广度明显健康才可跟随；趋势有效但缺少承接则关注回踩或等待，明显加速/集中不追涨，**分歧持续且动量减弱时即使尚未构成衰退预警，也可暂停买入**。上游高潮/衰退/失效且当下恶化亦可暂停；首轮除充分共振外不激进。
ETF 持仓动作**仅对Airtable核实已实际持有的ETF**适用，且须具备该ETF本人的有效行情与既定退出依据；否则只输出板块和ETF机会观察，不给假设性持仓卖出动作。ETF持仓动作为 继续持有/持有观察/减仓观察/减仓/退出；上游有效且正常/修复、动量稳定/增强可继续持有，普通分歧或单日持续分歧但跨日证据不足原则上持有观察；若同日持续分歧并出现进一步两类实质恶化，可在已有个股/ETF 自身弱化佐证时升级「减仓观察」，但该标签**不等于已执行减仓**，不能仅由板块状态名称自动卖出。确认的上游衰退迹象与跨日/当下弱化共振可减仓观察；上游高潮/衰退与实时显著恶化共振且价格结构证据充分才可减仓；上游失效且结构持续明显弱化、失效确认才退出。不凭单次分歧、七日累计收益为负或单一标签退出；首轮上游已明确衰退/失效且今天确认弱势，可按原规则触发。没有明确 ETF 代码不得猜测。

## 5. READY/WAIT 机会观察与实际持仓的双轨决策

**先区分实际持仓身份，再选择动作语义。**正式 READY/WAIT 仍全量读取 snapshot.trend_buy_stocks、保持相同排名和原始入场条件；但并非持仓证明。仅 Airtable 完整交易记录重建得到净持仓>0的股票可以输出持有/减仓/退出。未持仓 READY/WAIT 只输出机会观察，不生成任何止盈、止损或卖出动作。榜单中的股票如果也已持有，进入持仓分支；候选榜单标「已转持仓管理」，不再重复建议买入。

**未持仓 READY：**只有正式 entry_trigger 当前仍有效、price位于 entry_zone 且不超过 max_entry_price、行业和个股量价无失效证据，才能提示「条件可跟随」；超出上限不追价，不重新发明买点。**未持仓 WAIT：**一律仅表示观察、趋势改善或等待确认，不因盘中接近价格就变为READY。空仓机会枚举仍是 可跟随/关注回踩/等待/不追涨/暂停买入，但都不是已成交操作。

**真实持仓：**优先核验用户已明确记录的退出计划（盘中硬止损、收盘结构失效、分批止盈和重大事件退出条件），正式买点计划中的有效invalidation_price、invalidation_rule和exit_plan仅作无冲突的补充。若WAIT等记录中这些字段为null、用户条件模糊或与正式计划冲突，报告 EXIT_PLAN_UNCONFIRMED，只作持仓风险观察，不能自拟止损/止盈价。结构失效必须满足它**原本约定的确认时间和价格条件**。盘中触及「收盘失效价」只能预警；正式日线收盘确认前不得宣称结构已失效。独立、明确的盘中硬止损或预设分批止盈满足时可即时提示执行，不等待普通风险确认；不自动交易。持仓动作仍用 继续持有/持有观察/减仓观察/减仓/退出，但「减仓观察」只表示风险预警，不是正式减仓指令。

**结构/风险/动作解耦：**分别输出（1）结构状态：完整/待核实/按照约定确认失效，（2）风险等级：正常/观察/升高，（3）持仓执行动作：持有/减仓/退出及其独立触发依据。单次价格下跌、成本盈亏、板块广度或中位数弱化只能改变风险等级，不可直接推导实际卖出。普通风险升高和解除需**至少两个相隔15分钟以上的有效、独立盘中样本**确认，不满足则沿用前一已核实等级或显示待确认；不将重复读取同一快照当成两次确认。严重风险和预设硬止损不受这个普通防抖门槛限制。数据不足不得编造持续恶化或已经修复。

持仓不再出现在正式 READY/WAIT 时不能因此视为趋势失效；实际持仓可以独立监测，但非榜单持仓缺乏可信历史结构时，必须明确降低证据等级，只依据预先明确且可核验的退出条件决定真正的卖出提醒。行业/个股七日历史、正式收盘及同日先前扫描均不得互相替代。

## 5A. Airtable 实际持仓优先、只读、临时展示

保留现有监测频率、正式快照Gate、榜单冻结与 state READBACK，不新增监测任务，不自动交易；个人持仓记录只在当轮私人执行上下文中使用。**绝不将持仓代码清单、股数、成本、实际持仓身份或交易记录写入公开 GitHub**。快照新增的是不针对任何个人的全市场公开行情分片。

**连接与读取：**仅在正常完成第1节行情/日期 Gate 后，使用已连接的 Airtable 只读接口读取 base「交易复盘日志」（baseId=apphDsZysIUy8JciR）中的「交易记录」（tableId=tblEvj2Gc3QlLanpK）。取「股票代码」「交易标的」「操作类型」「价格（元）」「实际成交股数」「金额（元）」「交易日期」「记录日期」「失效条件」「复盘备注」，按接口 nextCursor 遍历至结束，不把首批分页误认为全部。调用不可用、权限失败、分页中断或字段缺失时标记 PORTFOLIO_CONTEXT_UNAVAILABLE/INCOMPLETE，仍执行全量板块及 READY/WAIT 机会观察，但不可推断空仓或输出个人持仓买卖动作；**绝不能把读取失败解释为没有持仓、没有风险，或通过外部市场数据兜底**。不写 Airtable、不过量重试。

**持仓核验与汇总：**
- 只按可核实的六位证券代码准确匹配；原始买入/卖出/清仓记录均须核对操作类型与成交股数，不能把记录日期冒充成交日期，不能把仓位比例、预估金额或备注当作已成交股数。先按交易日期与可核实顺序重建交易；若卖出先后顺序不明、重要成交数量缺失、标签不认识或记录冲突，标记该代码「持仓数量/成本待核验」，不得虚构净持仓。
- 对可核实的首仓/买入/加仓增加实际股数，对减仓/卖出扣减实际股数；清仓仅在实际已成交数量可核实时清零。净持仓 >0 才列为「Airtable 登记持仓」；=0 不列持仓；不推断未来成交或自动修改记录。买入成本按成交股数×单价核算，期间有卖出时仅在交易顺序可靠前提下以移动加权平均法估算剩余成本；缺失必要价格时只报告有效数量，不造成本；手续费、税费及滑点另注明未计。Airtable 数据仅是用户记录，不保证与券商实际持仓完全一致。
- 优先解析每只持仓的「失效条件」为**用户已记录的观察计划**。同一股票不同记录条件如不一致、过期、临时待复核或仅为文本模糊描述，则明示「待复核」并保留来源记录，不自行发明或上移止损价，不把买入成本当失效线。


**持仓与榜单的分流：**只按六位代码核验净持仓；命中当天正式 trend_buy_stocks 的使用其结构、相对强弱和历史上下文，但**只输出持仓管理动作**。未命中正式名单的真正持仓，按§5B核验同一行情采样时点的公开行情分片；不扩大候选名单，不创造正式rank，不重算上游行业研究。Airtable读取失败时必须标 PORTFOLIO_CONTEXT_UNAVAILABLE/INCOMPLETE，不能声称无持仓或对某代码发持仓买卖指令；READY/WAIT 可继续作非个性化机会观察。

**退出计划：**用户已登记的明确条件优先，冲突、过期或无法解析时注明计划待核验。实际买入成本仅用于盈亏参考，绝不是失效价；若约定「收盘跌破某价」，盘中低于只能写「触及待收盘核验」，绝不宣称有效收盘破位或直接减仓；快照和前一交易日盘中扫描都不是正式收盘价。缺少预定止盈计划不凭当日回撤自拟止盈。

**展示和落库：**先汇报板块/ETF，再展示实际持仓重点（包括正式榜单之外的持仓，展示数据来源、报价时点、风险与动作三层及退出条件证据），最后按正式rank全量列READY/WAIT候选，已持仓仅注明「转持仓分支」。不遗漏、不重复动作。state仍只持久化冻结的全量公开观察指标，不写私有持仓身份、交易计划或持仓专属state。不得借Airtable扩大市场机会池。

## 5B. 公共行情分片的持仓专用数据Gate

只在第1节行情、日期、正式Handoff数据Gate成功后，才按当轮Airtable已核实净股数>0的代码读取分片。索引为 snapshot.portfolio_quote_index；要求schema_version=1、kind=public_full_market_quotes_not_portfolio、status=available、trade_date与captured_at与本轮快照完全一致。代码必须是六位数字，prefix=code[:2]，路径严格等于 `research/intraday_quote_shards/{prefix}.json`，该分片实际完整UTF-8原文字节SHA256必须与索引sha256相符；其schema_version=1、result_kind=a_share_full_market_quote_shard、prefix、trade_date、captured_at必须匹配。只读取该code的报价，要求confidence=high/medium、price为正、quote_time确属当日且可信。任何失败输出 PORTFOLIO_QUOTE_UNAVAILABLE，绝不用过时行情、其他股票或外部网络填补。

分片同日 samples 最多保存三个**公共价格样本**，可核验普通风险的两次独立采样和15分钟跨度，但不意味着日线结构或此前收盘确认。未在榜单的已持仓缺少可核验历史结构/板块共振时，至多作风险观察与明确计划的触发检查，不能仅因价格变动推断结构失效。缺少可靠预设计划时统一 EXIT_PLAN_UNCONFIRMED。

分片生成和仓库提交仅包含全市场代码的公共报价，不筛选或泄露个人持仓。快照生成流程验证索引，不需要也不允许访问Airtable。盘中私下从Airtable读取与数据分片核对后才做持仓分析。整个过程不修改上游选股或板块榜，也不自动下单。

## 6. 唯一状态持久化、校验和错误

只允许写 main 上 research/intraday_monitor_state.json；绝不写入Airtable个人持仓明细/持仓列表、私人买卖动作映射或成本。State 仅为全量冻结候选的公共技术观察记录，不能被当成真正持仓交易动作。候选state中若保留旧版holding_action/previous_holding_action字段，仅为全部候选统一生成的**非私人、假设性兼容字段**，不得按Airtable持仓状态修改；实际持仓结论只临时输出、不落库。State 包含 schema_version、result_kind=a_share_intraday_monitor_state、execution_schema_version=2、trade_date/monitor_date、last_scan_at、snapshot_at、冻结 handoff 日期和全部身份/rank、industry_history/stock_history。每条行业记录保存 trend_name、上游状态、previous_state/current_state、previous_structure_momentum/structure_momentum、广度/涨跌/覆盖/中位数、previous_entry_action/entry_action、previous_holding_action/holding_action、reason 和 data_quality；个股每条保存完整身份与 rank、价格/相对行业、历史可用性和有效七日摘要、previous_relative_strength/relative_strength、previous_price_behavior/price_behavior、前后操作、买入区间关系、handoff 标志、reason、data_quality。

先构造完整对象并用可执行环境实际 JSON 序列化和 JSON.parse 同一个待提交文本，核验字段、日期、全部冻结身份和行业/股票覆盖、枚举值及 previous_* 仅来自同日更早已落库扫描。不接受省略、截断或目测检查。无法校验则 PREWRITE_JSON_INVALID，最多在同一有效快照和已核实状态下完整重建一次，仍失败则 STATE_WRITE_FAILED，绝不将失败轮次纳入历史。

写入前重新读取 main 目标文件最新全文及 blob SHA；**首次状态文件不存在时，核实GitHub返回路径不存在，并调用create_file建立本交易日初始状态，previous_*保持null**。只在实际写工具返回新 commit_sha、content_sha 后立即从 main READBACK 完整 JSON 和 SHA，比较日期、last_scan_at、来源日、冻结身份和排序、行业/股票各轮完整覆盖、必需字段及内容一致性。全部通过才报告 STATE_PERSISTED 且允许作为下一轮 previous_*。失败则 STATE_WRITE_FAILED/READBACK_JSON_INVALID/READBACK_MISMATCH，不冒称持久化或盲目二次覆盖。SHA_CONFLICT 必须重读、重做前置验证后最多重试一次。记录 READ_SOURCE、PREPARE_PAYLOAD、PREWRITE_JSON_PARSE、PREWRITE_SCHEMA_VERIFY、WRITE_REQUEST、WRITE_RESPONSE、READBACK、READBACK_JSON_PARSE、VERIFY 阶段及 attempt_id、日期、目标、工具、旧/新 SHA 和实际可见的脱敏错误；不可见 HTTP status/error.code/request_id 标 unavailable，不推测 403/409。

明确的 PRECHECK_BLOCKED（安全预检）不可将内容视为已落库，不得更换通道、拆分/编码/删减 payload 绕过；若执行环境许可，按既有受控规则延迟 30–60 秒，重新获取相同路径当前 SHA、验证相同语义的完整文本，以原工具最多原样重试一次；第二次仍被阻断立即停止并报告 PRECHECK_BLOCKED_REPEATED 和两次实际证据。其他权限/安全拒绝或审批要求须停止并如实报告。

## 7. 输出顺序与原则

标题“A股盘中交易执行监测｜北京时间 <scan time>”。先报告 captured_at、报价覆盖、正式交易日/Gate、板块七日历史及个股七日历史的可用性、持久化结果；Gate 未通过时不输出当轮交易动作。通过后按冻结顺序完整展示所有板块/ETF：方向、上游趋势、七日板块统计（真实中位数、上涨比例、样本覆盖）、板块 previous→current、动量 previous→current、空仓/持仓动作及具体证据。每个板块须分开展示「今日盘中变化」「七日累计历史」「可比的前交易日盘中截面」及「升级门槛是否满足」，列出参与判断的广度和中位数；跨日不可比要明确写原因，区分「分歧持续」与「衰退预警」，也须区分「减仓观察」与真正减仓。再按第5A节展示 Airtable 持仓重点关注（只使用冻结股票池内行情；缺数据须明示），最后按正式rank展示全部 READY/WAIT 的技术状态与未持仓机会建议；实际已持有的代码标明转入前述持仓管理，不重复入场或卖出建议。未持仓候选不展示内部兼容的 holding_action；无法核实持仓状态者标「持仓未知、仅非个性化机会观察」。无有效历史则明示，不漏股，不虚构。最后只补重大动作变化；无强信号时如实报告。永不反向修改上游趋势榜、趋势买点榜或正式 handoff。

## 8. 快照与交易计划契约

在任何本轮交易动作或状态持久化之前，必须核验 snapshot.schema_version=2、stock_handoff_kind=trend_buy_v2、source_stock_handoff_path=research/trend_buy_handoff.json、source_trend_buy_handoff_schema_version=trend_buy_handoff_v2，以及快照冻结名单、trade_date、source_run_id和validations全部匹配。如本轮有效基线缺失或快照schema不匹配，报告`NO_VALID_TREND_BUY_HANDOFF`或`SNAPSHOT_INVALID`。有效首轮`previous_*=null`，之后仅沿用同日已持久化扫描记录。

候选入场条件以 trend_buy_stocks[*].trend_entry_plan 的setup_type、entry_zone、entry_trigger、max_entry_price为准；实际持仓退出条件优先来自Airtable已明确的用户计划，只有不冲突且有效时才采用invalidation_price、invalidation_rule、exit_plan作为补充。盘中不得重新制定入场区或结构失效价。继续遵守板块/ETF证据、七日历史、持仓只读、日期Gate、写前JSON校验和GitHub commit+READBACK规则。

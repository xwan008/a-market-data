# A股板块趋势榜｜正式研究与趋势生命周期协议

> 本文件是「A股板块趋势榜」的**完整生命周期业务协议**。18:40首次扫描**先单独读取**不含历史主题案例的 `skill/TREND_DISCOVERY_NEUTRAL.md`，完成并冻结独立发现后，才读取本文件、历史账本与Python候选；06:40可以直接读取本文件。定时任务Prompt负责入口与执行顺序；本文件负责研究和发布规则；仓库现行校验脚本负责可程序验证的字段、阈值及数据一致性。本文仅整理既有规则，不改变原有T0/T1/T2、市场状态、ETF时机、优先榜资格/排序/数量、行业路由和下游JSON契约。

## 0. 先读：六条不可互相替代的原则

1. **当轮事实优先**：历史榜单是复核对象，不是当轮行情；基于真实时间戳、产业事实、行情和冻结的历史条件做独立判断。预测、量化辅助信号与资金估算不能伪装为已发生事实。
2. **无榜单锚定的独立发现优先**：18:40先只用当期中性市场/产业原始资料做全市场发现，并冻结首次候选；**冻结前不得读取上轮registry、handoff、旧优先榜、历史精选清单或本轮Python候选及其派生摘要**。冻结后再读旧账本逐项复核，最后用Python交叉查漏。旧主题不在首轮候选里，不构成该主题失效证据；Top20不是研究或新仓榜上限。
3. **四个判断维度分离**：产业/商品的`trend_state`与`lifecycle_status`、A股板块的`market_state`、产业受益映射及当期新仓资格各有独立证据；没有合格买点、A股涨幅不如海外或映射不完整，不能据此人为降低产业等级。
4. **抗噪声，不抗风险**：普通单日分歧不机械降级，普通单日反弹不机械升级；但板块当日集体下跌、关键结构被确认破坏或产业核心驱动被重大新事实证伪时，必须及时按规则迁移，不能机械“等明天”。
5. **历史只能追加**：不为迎合今日结果改写旧交易日状态、首次出现时间、证据或预测；历史源缺失须标记未知，不制造历史。
6. **正式发布必须真实完成**：全部研究和数据Gate、状态迁移Gate、GitHub提交及READBACK均通过，才能称当轮结果正式落库；任何环节失败，应准确报告，不能编造PASS或用草案冒充正式榜单。

**规则冲突处理**：本文件为业务原则；脚本及对应测试定义现行可执行字段与量化校验边界；正式registry/handoff依现行schema。出现明显冲突或执行条件缺失时，停止受影响的正式发布并报告具体冲突，不得自行选择宽松解释。实现门槛若需改变，必须先版本化修改程序与测试，不能在报告中临时“豁免”。

## 1. 两种运行模式与18:40顺序

### 1.1 06:40｜隔夜增量复核

只读取上一有效完整A股交易日**已成功提交且READBACK**的正式registry，以及截至早间可核验的新事实；保留原趋势状态与实际核验日期，按原`previous_trade_date`和数据Gate做增量复核。海外黄金/原油隔夜走势可触发风险观察和条件情景复核，但不能冒充当日A股完整收盘数据，也不生成新的当日正式handoff。

基线文件缺失、日期不匹配、结构无效或`BOOTSTRAP_PARTIAL`时报告`REGISTRY_BASELINE_UNAVAILABLE`，不能从Top榜或历史传闻重构“已确认的最新基线”。

### 1.2 18:40｜完整收盘研究：强制八步

1. **收盘有效性Gate**：只先读取 `skill/TREND_DISCOVERY_NEUTRAL.md` 和中性schema/行情质量检查规则；核实交易日、完整收盘行情、日期、覆盖和质量。这时只准用原始全市场行情、未筛选行业/公司资料和公开产业事实；**不得提前读取本生命周期协议（其中含有具名历史板块案例）、旧registry/handoff/Top榜或本轮Python候选输出**。失败如实报告，不宣称完成研究。
2. **无历史榜单的全市场独立发现**：仅依据本轮时点可得的政策、商品、供需、订单、盈利及全市场量价、结构，从全覆盖的行业/产业问题出发找候选；不能让昨日榜单确定扫描范围、查询词、研究预算或待选顺序。允许查看历史原始行情与公开产业资料，**不允许查看已经被旧趋势榜筛选/赋级的主题名单或结论**。记录真正扫描过的市场范围、缺口、来源与截止时点。
3. **立即冻结第一轮发现结果**：在读取本完整生命周期协议、上轮registry/handoff/历史精选名单和本轮Python候选之前，按中性规范冻结独立发现的规范方向、已核实行业代码、支持/反证、真实截止时点和候选/排除理由，包括当轮无新发现的事实。可使用 `scripts/validate_trend_discovery_checkpoint.py` 做第一阶段文件结构检查；独立预提交快照需留真实Git SHA与READBACK。**结构校验与模型自述均不证明认知隔离**；如未真正技术隔离，标声明式或UNVERIFIED。此后才加载本文件，进入历史全量复核；后续不得倒填首轮结果。
4. **加载完整协议、读取历史账本并逐项复核**：第一轮冻结完成后才读取 `skill/TREND_REGISTRY_PROTOCOL.md` 全文及正式校验程序，然后从main读取最近一次正式提交并READBACK的完整`research/trend_registry.json`、真实Git blob SHA、交易日、全部旧趋势和`state_history`，保存只读previous副本。按各主题完整历史复核确认/退化/失效/恢复条件；关键历史证据缺口才回读旧Git提交及当时冻结数据，结合当期可比1/3/5日和必要的10/20日及更长行情结构。**历史记录只用于旧主题生命周期复核，不得倒写第3步独立名单；旧趋势首轮未命中不等于失效**。
5. **本轮Python查漏与证据交叉**：完成旧趋势复核后，读取同日有效的Python行业/主题发现清单；核实模型首轮遗漏、旧主题异常、程序独有线索、行业路由及实际发现来源。Python分数和Top20不能代替产业研究、直接改变正式市场状态或抢占新仓优先级。
6. **合并去重并分层决策**：合并第3步冻结的首轮发现、第4步复核的全部历史主题及第5步核实的Python补充线索，按真实产业身份去重；分别判断产业/商品第一锚及T等级、A股market_state、受益映射和当期新仓/ETF资格。历史独有主题归入`recovery_candidates`/既有趋势复核审计，**不可算作本轮“模型独立首发”**；历史完整池不得因首轮漏扫而被删减。依据第2—5节区分正常波动、真实结构破位及研究缺口。
7. **预提交审计及正式发布**：生成完整proposed registry但先不写正式文件，按第8节校验状态历史和客观证据；通过全部Gate后先提交registry、READBACK，再按原规则生成handoff、提交并READBACK。
8. **完整中文报告**：依第9节分开展示独立首轮发现、历史趋势去向、Python补充、完整趋势池、优先榜、失效条件、外部商品展望及真实发布结果。

## 2. 四层研究对象与数据含义

| 研究层面 | 正式表达 | 只有什么证据能改变它 |
| --- | --- | --- |
| 产业/商品趋势与生命周期 | `trend_state`：T0/T1/T2/待核验；`lifecycle_status`：有效/待复核/已失效 | 商品供需/价格结构、政策、订单、盈利及产业自身驱动的新增事实 |
| A股板块市场状态 | 原`market_state`枚举：新异动、观察、候选趋势、趋势确认、高潮/衰退、失效 | 真实可比的板块量价、广度、相对强弱、核心/中票扩散、承接及关键结构 |
| A股受益映射 | `industry_codes`/`industry_names`及研究证据 | 实际公司业务与上下游利润传导、核对的申万行业代码和有效样本 |
| 新仓优先与ETF时机 | `in_new_position_priority`、handoff | 原新仓资格、风险收益比、ETF时机、既定排名及数量规则 |

- **A股市场状态失效不等于产业失效**：国内板块可以已跌破结构而海外商品仍强；仅前者证据成立时允许降低`market_state`，不能同步凭空降低T等级或标记产业`lifecycle_status=已失效`。海外商品走强也不能反过来强制标记A股趋势确认。
- **退出新仓榜不等于退出完整趋势池**：高位拥挤、缺合格买点、映射不全都可能使`in_new_position_priority=false`，但不自动改变原产业和市场状态。新主题未核实路由可留待研究，不编造行业代码强制写handoff。
- **未核验不是当日确认**：证据不足时保留最后可追溯的旧状态、原核验日期，并在新研究审计注明待复核/分歧，不把旧结论称为本日已经充分确认。

## 3. 状态迁移准则：连续性与及时性

下表均为**有来源、有日期、符合既有规则**的状态判断，不因一次交易感受、程序未命中或“谨慎”主观改分。不另创造通用固定N日等待门槛。

| 路径 | 应采取的判断 |
| --- | --- |
| **保持HOLD：正常回调/局部分歧** | 单日广度收缩、少数子行业疲软、个股回调、ETF下跌或Python未发现，且原确认的产业/市场结构未被证实破坏：状态不变、保留原核验时间，另记风险；不制造状态历史变更。 |
| **下降CHANGE：持续结构弱化** | 同口径多日价格结构被破坏，伴有相对强度/广度等独立反证：按既有标准降级A股市场状态，证据需能解释为何不只是调整。 |
| **下降CHANGE：当日系统性退潮** | 当日真实收盘数据已证实板块多数成分股显著走弱、核心与中票同步承压、相对市场偏弱、已有来源的关键支撑有效破位：可**当日**降低市场状态，不等待连续数日；按第8.2节验证，不得仅凭几个龙头或一项广度判断。 |
| **下降CHANGE：产业核心证伪** | 重大供需、政策、商品结构、订单/盈利驱动被真实新事实证伪：可当日改变产业T等级/生命周期，并另行判断A股市场状态。不能将权益集体下跌当成产业基本面证伪。 |
| **升级/恢复CHANGE** | 新异动遵循原早期发现规则；旧趋势恢复须符合原确认条件和结构修复，不能因隔日反弹、单日广度回升就频繁恢复确认。 |

**优先级**：已经核实的强反证优先于防抖；无充分反证时不得为回避风险主观降级。前一轮的「高潮/衰退」也只是历史判断，必须用今日事实重新验证，不能自动判定当日延续衰退。严重集体退潮和产业趋势存在可以同时成立，报告分开记录。

**用于回放的反例而非预设答案**：银行内部扩散减弱但中期价格结构未破坏时不只靠单日疲软降级；国际原油强但本地石油股弱时分层判断；黄金回调/反弹两日间不靠单日广度反复在观察与候选间跳转。如果这些案例后来出现真实破位证据，则按新事实执行迁移，不为保持案例结论而拖延。

## 4. 国际商品、产业传导与条件性前瞻

### 4.1 A股上下游映射

有海外第一锚的主题须分别研究国际商品趋势、A股实际业务传导和本地市场结构。直接受益、间接受益、混合、成本受损和待核实关系分别列明，不能因同日上涨就断言相同因果。

原油示例：上游开采、综合油企、油服/工程、炼化贸易及油轮运输受不同驱动。中国海油、中国石油、中国石化等须核实实际主营结构；招商轮船、中远海能等油运主体需单独检查运价、运力、航线、燃油及保险成本。集团名不能当单一A股证券，集装箱、干散货和港口也非天然油价受益者。

`research/theme_industry_catalog.json`现有`oil_gas`核心研究代码为`S750101`油气开采、`S750201`油田服务；`shipping_ports`核心为`S421101`航运、`S421102`港口。还可调查`S750202`油气及炼化工程、`S750301`炼油化工、`S750302`油品石化贸易与航运细分。目录仅是**版本化研究聚合口径**，不是受益公司的穷尽清单或下游授权名单。实际证据不足记录`MAPPING_RESEARCH_INCOMPLETE`（仅审计文本，不新增状态枚举），不改变产业等级，也不编造新的三级行业映射。

### 4.2 5/10个境外交易日展望与回验

18:40对黄金、布伦特/WTI、铜等有可核验国际第一锚的主题建立未来5/10个**相关境外市场交易日**的条件性研判，黄金为优先实测对象：

1. 冻结截至本轮真实可用报价的来源、时间/时区、价格、币种及现货或期货合约信息；境外盘中价不冒充最终收盘，不混用现货/不同月份期货连续序列。
2. 如有可靠数据，研究已发生5/10/20境外交易日高低点、结构支撑/阻力和最重要1—2个驱动。黄金可核验美元、美国实际利率/政策预期、央行与黄金ETF需求、地缘风险等，但不要堆砌未被验证的宏观因素。
3. 给未来5日与10日各自的基准方向、上行/下行条件、失效/反证触发和高/中/低置信度（或资料不足）；不虚构价位目标和精确概率。
4. 在`scan_audit.forward_outlooks`记录`trend_name`、`as_of_trade_date`、`quote_timestamp`及时区、`source_urls`、`horizons=[5,10]`、`baseline`、`upside_case`、`downside_case`、`key_driver`、`invalidation_trigger`、`confidence`、`data_quality`。报价与关键资料无效时标`OUTLOOK_DATA_INSUFFICIENT`。
5. 从旧正式Git提交引用原版展望，在`scan_audit.forward_outlook_reviews`记录`original_as_of_trade_date`、原情景、当前可核验变化、偏离和是否到期；只在相应5/10日结束后评价准确性，未到期仅作阶段观察。历史展望只引用不改写，样本少时不宣称预测优势。

**独立性**：预测不属于已发生的`supporting_evidence`，不能直接触发A股/产业状态迁移、交易买卖或新仓排序，也不得阻止真正已证实的失效降级。06:40只可更新隔夜风险观察，不重写旧版冻结展望。

## 5. Python交叉发现、分类目录及来源归因

### 5.1 辅助程序的职责和质量

- **先无榜单独立扫描、再历史复核、后Python**：先读中性 `skill/TREND_DISCOVERY_NEUTRAL.md`，模型首轮名单仅来自第1.2节第2—3步，包含规范主题、已核实的申万三级代码、原始行情/产业证据、截止日期及覆盖缺口；读取它之前不能接触上轮registry、handoff、昨日精选榜、本轮Python候选或其转述。第4步历史复核独立记录`recovery_candidates`，不倒填第一轮名单；第5步再读Python。本轮Python候选不得提前泄漏给“首轮模型发现”。
- `data/research/sector_discovery_snapshot.json`和`data/research/sector_discovery_audit.json`按实际交易日、schema、status、覆盖及来源校验：`model_research_candidates`通常Top20、`theme_research_budget`仅限制**程序辅助复核**；`candidate_overview`、`deferred_candidates`及`all_industry_metrics`用于补查。STRONG/EMERGING与Python分数是量价线索，不是趋势、排名或股票买点。
- `research/theme_industry_catalog.json`是版本化主题—申万三级行业研究目录：`core`参与去重成分股量价聚合，`related`只作旁证，不自动交接。申万二级基础分组是统计分类而非独立产业主题；跨主题行业可重叠，同一主题内个股不得重复计数。某历史快照覆盖331个申万三级行业、131个基础组、17个研究主题，**这些是版本快照数量，不是永久阈值或发现上限**；以本轮真实分类版本及审计覆盖为准。
- `data/research/theme_evidence_snapshot.json`仅为精简辅助快照。须核实同一`trade_date`、`schema_version=1`、`result_kind=a_share_theme_evidence_snapshot`、`status=COMPLETE`、`no_trade_signal=true`、`auxiliary_only=true`、`decision_authority=legacy_model_driven_trend_research`、`point_in_time_eligible=true`及研究目录时间口径。`research_candidates`是正向线索，`tracked_theme_alerts`是旧主题风险线索，`unmapped_industry_alerts`指未关联到独立研究主题的行业异动；`SW_L2_TAXONOMY`是分类统计组、`RESEARCH_THEME`是研究主题量价组，均须产业独立核验。
- 辅助数据缺失、过期、部分覆盖或`RETROSPECTIVE_MAPPING_SMOKE`等日期/目录冲突时，报告`DISCOVERY_UNAVAILABLE`及真实缺口，**不因辅助程序缺失本身阻断已通过原全部Gate的完整模型研究**；但也不能冒充程序扫描已经完成。采用第8.2节当日集体退潮特定通道时，对它要求的客观行业证据另行强制核验。
- 同日强势分类/多主题重叠要去重；程序新增线索未证实则保留待研究或排除理由，不能仅凭同涨/分类相近合并主题，也不能让程序遗漏导致旧趋势降级。程序扫描量化阈值未经验证预测力，不得被当作正式选股胜率。

### 5.2 首次发现归因（只承认真实顺序）

`BOTH`：模型第一轮和同日Python正向候选都明确命中；`MODEL_ONLY`：模型第一轮命中，Python同日有效覆盖但未正向命中；`PYTHON_ONLY`：模型第一轮未发现、从同日Python正向候选进入本轮研究（即使最终排除也不改其来源）；`UNVERIFIED`：先后顺序、来源或行业身份无法核实。共同发现不代表两条独立产业事实；仅有`tracked_theme_alerts`不是首次发现；旧趋势未被Python命中不证明首次一定来自模型。

在`scan_audit.discovery_attribution`保留兼容字段`trade_date`、`method=MODEL_FIRST_THEN_PYTHON`（仅为**旧有发现来源字段标签**，完整执行顺序仍是“独立首扫→历史→Python”）、`model_first_pass_frozen`、`model_first_pass`、`python_snapshot_trade_date`、`python_snapshot_blob_shas`、去重并集`candidates`及`attribution_status`；candidate包括`direction`、`industry_codes`、`origin`、`model_first_pass_hit`、`python_positive_hit`、`python_source_types`、`disposition`（INCLUDED/PENDING/REJECTED/MERGED）、`canonical_trend_name`与`reason`；历史异常另记`recheck_alerts`。可在可扩展审计中增加`pre_history_scan`（冻结时点、资料截止日、扫描覆盖及缺口、`history_list_unread_at_freeze`声明、冻结名单快照的commit/blob SHA及READBACK状态），**只增加审计元数据，不改变schema_version或handoff**。原有`independent_new_candidates`仅记首轮真正独立候选；`recovery_candidates`只记读取历史后额外找回的主题；`post_program_additions`只记Python后经研究补充的主题。

只有**独立扫描结果在读取历史账本与本轮Python候选之前已真实提交独立冻结快照、成功READBACK，并有可追溯的Git commit/blob SHA及运行顺序记录**，才可将这一轮先后顺序列作`VERIFIED_PRECOMMIT`；仅在同轮最终JSON中声明冻结属于`DECLARED_IN_RUN`（自述流程顺序，**不是独立隔离已经被外部证明**）；先后不可核实时为`UNVERIFIED`。Git快照本身也不能证明模型对旧主题没有来自先前会话的记忆，因此“完全隔离”必须依赖确实不含旧榜信息的独立上下文，不能凭程序命名或字段自报。来源无法验证不应强制新增Git提交或阻断其他已合格的原正式发布，但不得冒称已严格独立。本规则上线前的历史首次来源，以及2026-10-12及以前无法核实者，不能事后回填新来源。06:40不制作新的发现来源样本。报告应区分“首轮主动发现”“读取历史后找回”“Python新补充”“来源不明”，不只在JSON里留标签。

## 6. 资金流向与量价配合（纯辅助）

资金流向**不构成**新的趋势确认、降级、排名、入榜、ETF或新仓资格Gate；原价格结构、广度、相对强弱与龙头/中票扩散优先。

同源可比时观察当日/5日/20日净流向、区间天数、相对成交额占比、对应价格和成交量/额；这些时间窗口重叠，不可当独立证据。不同平台/分类不直接求和，放量不能推断净流入。资金估算不等于真实机构仓位；涨价净流出、流入却滞涨应描述背离，不事先解释为吸筹/出货，也不凭单日流出判趋势结束。可展示“资金与量价印证/背离/短期转向待确认/无明确增量/不可用”，注明窗口、日期和来源；可靠描述可放现有registry`supporting_evidence`/`contrary_evidence`，标“仅资金辅助观察”，不增加handoff字段。无数据、过期或不可比只记未验证，不阻断其余合格研究。

## 7. 正式JSON契约、完整趋势身份与初始化

### 7.1 两份输出的分工

- `research/trend_registry.json`：跨轮完整趋势池、全部旧主题去向、待复核与已失效历史、当期研究证据、`scan_audit`、`recheck_queue`；即使退出新仓榜也必须保留研究连续性。**18:40此文件在独立首轮冻结后读取，不得将旧榜单当成首轮搜索输入。**
- `research/trend_handoff.json`：沿用原`schema_version`及`signals`格式，仅保留符合原新仓资格、排序及数量的方向；其名称和顺序必须与当轮registry里`in_new_position_priority=true`主题一致。不因新的研究审计扩充下游公司池。
- `research/theme_industry_catalog.json`只是研究目录。可用`scripts/validate_theme_handoff_routes.py`核对申万三级行业代码/名称、同日`data/low_risk/index.json`、有效非空公司池和manifest。代码路由通过不代表相关公司全体真正受益或已符合独立股票买点判断。

### 7.2 Registry schema_version=1

顶层：`schema_version=1`、`result_kind=a_share_trend_registry`、`trade_date`、`generated_at`、`timezone=Asia/Shanghai`、`status=COMPLETE`、`trends`、`invalidated_history`、`recheck_queue`与`scan_audit`。`scan_audit`保留`full_market_scan_completed`、`previous_registry_trade_date`、`previous_trend_count`、`previous_trend_rechecked_count`、`new_trend_count`、`pending_revalidation_count`、`invalidated_count`、`new_position_count`、`evidence_cutoff_trade_date`及原有其他审计字段。

每条趋势至少：`trend_name`、`trend_state`、`market_state`、`lifecycle_status`、`first_seen_trade_date`、`last_verified_trade_date`、`industry_codes`、`industry_names`、`in_new_position_priority`、`supporting_evidence`、`contrary_evidence`、`invalidation_condition`、`change_reason`、`state_history`。证据注明时点、来源，状态迁移记录原态/目标态/日期/原因；待复核保留历史最后核验日期，不冒充当日确认。

**身份/历史保护**：`first_seen_trade_date`不得改；旧`state_history`必须是新历史的完整原样前缀，只能追加本轮事件。现行迁移脚本按`trend_name`匹配，因此不能在本轮静默改名、拆并、重命名或删除旧trends条目；已确认失效也保留完整原身份和历史，同时在`invalidated_history`记录。以后要真正迁移身份须先补充可验证的正式迁移规则与测试，不得绕过脚本。历史缺口用`recheck_queue`标`provenance/unknown`，不得补造2026-09-17之前无法恢复的记录。

初始`BOOTSTRAP_PARTIAL`仅代表从有来源的资料恢复待验证主题，不等于完整正式榜。首轮有效18:40要全市场复核旧主题、待复核队列后才能生成COMPLETE。**现行迁移程序要求previous和proposed均为COMPLETE**，不能把BOOTSTRAP_PARTIAL伪装为COMPLETE取得PASS；若遇真实初始化情形而工具不支持，应报告并经正式初始化路径处理，不跳过迁移Gate。

## 8. 状态迁移预提交Gate及正式发布

### 8.1 全量旧主题的迁移审计

本轮先完成“无榜单首扫及冻结→历史全量复核→Python查漏”，**然后**生成未提交的完整proposed registry，并在`scan_audit.state_migration_gate`填`mode=full_close`、`previous_registry_trade_date`、`previous_registry_blob_sha`（真实40位Git blob SHA）、`current_trade_date`。对previous中**每一个trends条目**恰好一条`reviews`，包含`decision=HOLD/CHANGE`、旧新`market_state`和`trend_state`、`reason`与`evidence`；所有实际状态或生命周期变化，按校验程序要求在`state_history`追加日期、原态、目标态。

`evidence`至少用`dimension`、`direction=SUPPORT/COUNTER`、`impact=NORMAL/STRUCTURAL/CRITICAL`、`trade_date`、`source`、`finding`描述；多日结构注明`window_trading_days`。使用的维度为`COMMODITY_ANCHOR`、`INDUSTRY_FUNDAMENTALS`、`SUPPLY_DEMAND`、`MARKET_STRUCTURE`、`MARKET_BREADTH`、`RELATIVE_STRENGTH`、`MAJOR_CATALYST`。发生状态变化必须有日期晚于上一基线交易日的真实新证据。程序能检验日期、来源形式、历史前缀、覆盖和证据组合，但不能独立证明原始行情/产业事实为真；不能编造`CRITICAL`绕过独立核验。

### 8.2 当日集体退潮快速通道

仅当真实完整收盘数据显示A股板块普遍明显下跌、核心/中票共同走弱、相对市场偏弱、**事先形成的关键价格支撑**被有效破坏时，才使用此通道及时降低A股`market_state`；产业T等级与产业`lifecycle_status`另需自身驱动的反证才能降级。

需用同日完整`data/research/sector_discovery_audit.json`对照行业样本覆盖、上涨广度、收益中位数及相对强弱；其行业数量以本轮实际有效目录和文件为准，**不得把旧331个行业当成永久固定数量**。在本主题`reviews[]`写`same_day_collective_breakdown`（`trade_date`、`support_breaks`数组），每条支撑记录`industry_code`、早于当日的`reference_trade_date`、`support_level`、当日真实`observed_close`和`source`。同时给出当日`MARKET_STRUCTURE`、`MARKET_BREADTH`、`RELATIVE_STRENGTH`的结构性反证。

紧急通道执行CLI时**必须**传`--sector-audit`指向合格当日文件；程序以现行脚本/测试中的覆盖、跌幅广度、相对强度及支撑验证规则作为质量底线，这些门槛不是经独立回测确认的投资胜率。审计文件不能替代成分股层面的真实核查，事后挑选高点当支撑、缺报价格或宣称模型“严重”都不能冒充快速通道已通过。若通道资料不足，仍可使用已有其他合法状态迁移路径核查实际反证，但不能假冒PASS，也不能主观宣称今天已确认原趋势仍然有效。

### 8.3 实际运行、发布、READBACK与异常

在提交任何正式registry/handoff前，用冻结的真实previous/proposed及Git blob SHA执行仓库现行程序（路径示意；应先核对程序接口）：

~~~bash
python scripts/validate_trend_state_migrations.py \
  --previous /tmp/previous_registry.json \
  --proposed /tmp/proposed_registry.json \
  --previous-blob-sha <真实上轮blob_SHA>
# 同日合格主题辅助快照可附加 --snapshot <路径>
# 当日集体退潮通道必须附加 --sector-audit <同日行业审计文件>
~~~

在本轮任何正式写入前，除上述状态迁移Gate外，还应在工作目录中生成**尚未发布的完整handoff草案**，运行 `scripts/validate_trend_publication_pair.py --registry <proposed_registry> --handoff <proposed_handoff>`，检查真实同一交易日、优先榜主题名称和顺序、产业/市场状态及行业路由一致。此pair Gate的历史回放开关 `--historical-baseline-only` **仅供旧榜无迁移审计的历史检测，禁止用于新正式发布**。

只有上述**状态迁移Gate和pair Gate都真实退出码0且status=PASS**，且原独立研究、交易日、行情/行业覆盖、JSON结构/身份等Gate全部通过时，才：
1. 首选在同一GitHub **Git tree/commit**中原子提交两份已经预校验的proposed文件，并用**不强制覆盖**的分支HEAD比较/快速前进提交；HEAD已经改变时重新冻结基线并重新校验，不可force覆盖别人提交。
2. 在同一新commit下分别FETCH、完整解析并READBACK `research/trend_registry.json` 和 `research/trend_handoff.json`，核对日期、主题去重/历史/审计、优先榜实际资格和名称顺序、行业路由及新blob SHA。若当前可用执行工具暂时无法安全完成原子提交，应保留原先registry先提交、READBACK、再提交**预先校验过的**handoff并READBACK的降级路径；中途失败必须报告**非原子部分成功**，不得假冒完整成功。切换原子写入方式应先通过不修改main的演练。

状态迁移程序或pair程序阻断/无法实际执行时分别报告`STATE_MIGRATION_GATE_BLOCKED`或`PUBLICATION_PAIR_GATE_BLOCKED`；独立研究/覆盖不足报告`REGISTRY_INCOMPLETE`，写入/回读失败报告`REGISTRY_WRITE_FAILED`/`REGISTRY_READBACK_FAILED`及实际阶段。本轮不得发布宣称成功的新榜单、绕过安全拒绝、另走未批准写入通道或把草稿充当已落库数据。如果只成功提交registry而handoff失败，须如实说明哪些文件已持久化、哪些未完成，不声称两份原子提交成功。

### 8.4 旧账本产业与市场失效语义审计（不自动改历史）

使用 `scripts/audit_trend_lifecycle_semantics.py` 只读检查既有 `lifecycle_status=已失效` 是否留有商品/供需/订单/产业基本面等**结构化原始反证**。输出 `REVIEW_REQUIRED` 仅代表历史证据链不够清晰，不能证明原判断错误，更不能在未研究、未通过迁移Gate时静默把过去 `已失效` 改写成有效。2026-10-13的只读审计快照保存在 `research/audits/2026-10-13_lifecycle_semantics.json`；后续研究根据新事实对今日状态按正常迁移规则重新判断，旧结果只能保留并追加解释。含 `blob/main` 的历史证据链接不是不可变快照，回放时要查对应旧Git SHA，未来审计新证据优先记录不可变源码版本及内容SHA。

## 9. 报告与历史回验

当轮中文报告保持原有主要结构：**完整趋势池（含待复核、高潮/衰退和已失效去向）→当期新仓优先榜→ETF时机/失效条件→全部旧趋势状态变化→商品5/10日条件展望及上一轮回验→发现来源与补研缺口→真实GitHub持久化结果**。在发现来源部分明确列出**无榜单首轮独立发现、历史账本恢复的旧主题、Python补充方向**，并注明首轮“先于历史”的可验证程度；历史记录不能被追认为当轮模型首发。每个完整池和新仓榜条目直接标真实首发来源（模型/程序/共同/未核实），不能仅藏在scan_audit。分别展示产业是否有效、A股市场是否有效、映射覆盖和是否适合新仓。单日集体退潮发生时明确当前市场状态降级原因及产业第一锚是否仍在；辅助资金有数据才展示，不要求为空凑数。末尾列真实commit/content SHA和READBACK，若失败则列阻断阶段。

**前瞻评价基线（新增）**：使用 `scripts/build_trend_outcome_cohort.py` 按当轮正式registry及同期报价/行业索引的实际内容SHA生成独立只读cohort，不更改registry/handoff，也不把首次发现日当成有可核验买点的策略进场日。历史起始对照样本为 `research/audits/2026-10-13_prospective_outcome_cohort.json`；目前该样本仅锁定21个主题的状态、研究行业代码及来源SHA，5/10/20日收益与失效识别延迟均为右删失、待未来真实完整交易数据评估。源行情与行业索引文件的截至日期尚须独立核验，未通过核验前不计算或宣传收益统计。若未来研究想计算真实收益，还必须恢复冻结当天的**股票成分与基准价格**，不能用未来新加入的成分倒灌。

严格历史回验：只能使用当时实际Git SHA冻结的`data/latest.json`、`data/research/company_industry_index.json`、`data/research/full_market_price_structure.json`及同交易日合格资料；日期不匹配或缺文件则该日期不可评价，不能拿未来分类和新闻补齐。衡量发现后及正式入榜后5/10/20个交易日表现、相对全市场变化、生命周期、1—3日状态反复、误降级和实际失效识别延迟，说明样本量、右删失、未上榜候选、重叠主题与市场环境。下一/下两个交易日均走弱的误报代理**不等于投资亏损率或炒作概率**。MODEL_ONLY/PYTHON_ONLY/BOTH来源标签只表示发现渠道，不能靠胜出个案得出因果；样本不够不宣称验证出预测优势。新阈值若要改须先独立回放、版本化协议及脚本并加测试，不能为银行、石油、黄金或粮食个案反向调参。

## 10. 一页执行检查表

- [ ] 06:40直接按正式协议增量；18:40先读**中性发现规范**并验证交易日，在首轮冻结之后才读完整生命周期协议与历史榜。
- [ ] 在接触旧registry/handoff/历史精选和本轮Python候选之前，先完成**无榜单全市场独立发现**并冻结首轮候选、证据时间、扫描覆盖；记录隔离/冻结的实际可验证程度。
- [ ] 冻结后才读取最新完整账本及真实SHA，完成全部旧趋势状态复核；只在历史缺口时回溯旧Git版本。历史找回主题不能冒充首轮新发现。
- [ ] 历史复核后才读取本轮Python候选，交叉查漏；合并三路结果且旧主题不因首轮未命中被遗漏或降级。
- [ ] 产业/商品、A股市场、映射、新仓资格分别判断；正常噪声不改判，真实集体结构破位不延迟。
- [ ] 外部商品预测、辅助资金与程序候选只作适当证据，不混同已发生事实。
- [ ] 旧主题全覆盖HOLD/CHANGE审计，历史前缀不改，新主题有当轮可验证研究证据。
- [ ] 集体退潮通道经同日行业快照、此前确认的结构支撑和真实收盘验证。
- [ ] 所有研究/数据/状态迁移Gate和**双文件pair Gate**真实PASS；优先原子提交两份草稿并分别READBACK，不具备原子写入条件时完整报告逐文件提交/失败状态。

**维护原则**：新增规则只在本协议对应唯一章节修改，字段/阈值的具体实现同步至程序及测试；定时任务入口只负责调用，不重复堆叠这份文档。

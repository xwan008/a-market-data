# A股趋势买点榜｜唯一正式业务规则

## 1. 目标
本文件是 main 中唯一正式执行入口。每日依次执行行业路由、Python候选与资金冻结、模型研究及选择、Python独立交易风控、正式发布与核验。完整保留研究证据用于前瞻验证；不得自动下单，不新增定时任务、平行生产榜单或独立采集系统。

权威职责：本文件定义执行链、程序预筛、资金采集、交易风控、发布、异常恢复和报告验证；[行业路由协议](TREND_HANDOFF_ROUTING_OVERRIDE.md) 唯一定义行业准入与身份映射；[模型研究协议](TREND_BUY_MODEL_TOP1_RESEARCH.md) 唯一定义研究证据、选择门槛、决策优先级和模型交接格式。每轮从 main 实时读取本文件及全部引用的生效协议、程序契约、安全与发布规则；程序负责确定性计算和校验。实际契约冲突时阻断，不自行采用替代规则。

## 2. 唯一执行链
1. 核验北京时间参考日为合法交易日；读取同一完整交易日且通过正式配对Gate的 `research/trend_handoff.json`，完整执行 [行业路由协议](TREND_HANDOFF_ROUTING_OVERRIDE.md)。不合格路由停止发布。
2. **零合格趋势可无新榜**：若本轮已完整发布且配对Gate通过的 `research/trend_handoff.json#signals=[]`，这是合法的 `NO_ELIGIBLE_CONFIRMED_TREND`，当天不启动Top5个股深研、不生成或覆盖新的 `research/trend_buy_formal_result.json` / `research/trend_buy_handoff.json`，并在19:00报告明确注明“无合格确认行业／未发布当日新买点榜”；不得重用前一日股票、伪造空公司工作集来凑READY/WAIT或把正常空信号当成失败。若存在合格信号但数据不齐或映射不合格，则仍BLOCK，不得以空榜掩盖数据质量错误。
3. 校验 data/low_risk/index.json、manifest和全部part，读取一次并Freeze公司working set；不得用旧行情、缺失部分或未来证据。
4. 按第5节唯一程序预筛，由 `scripts/prepare_trend_buy_candidates.py` 生成 `research/trend_buy_candidates/latest.json`，核验 main 中同日真实Python冻结结果、`CANONICAL`预筛标识、源数据与财务SHA、原始顺序及每SW3最多五席。
5. 技术输入仍由行情数据分片和冻结历史工作集生成；正式程序对全行业执行有成本约束的Python指标和截至当日完整65根以上日K，同一价格口径差异>1.5%或未来K线一律拒绝；仅对被筛入的5家公司进一步构造完整近端结构与120～180日阻力，用于后续独立风险核验。拒绝读取未来价格或生成虚构预期，拒绝因涨得多机械排后、因价格低机械排前。
6. **先Python后模型**：完整执行第6节资金冻结和产物核验；模型依 [模型研究协议](TREND_BUY_MODEL_TOP1_RESEARCH.md) 对首次研究的全部冻结候选、恢复时仅INCOMPLETE组的全部冻结候选开展研究。不得以模型重建程序名单或资金。
7. 按最新价量数据确定个股阶段：INITIATING（启动）、PULLBACK（分歧回踩）、REACCELERATING（承接后再加速）、REPAIRING（结构修复）、COOLING（新入场优势下降）、FAILED（确认结构失效）、TRANSITION（证据尚不足）。MA20/MA60是背景而非淘汰红线；单纯低于MA60不得直接DROP，单日放量也不得直接宣布有效趋势。
8. **先识别本次交易形态，再计算与其一一对应的失效位与赔率**。BREAKOUT必须有当日已确认的历史突破关口（已有价格/量能/收盘证据），以**本次突破关口被有效重新跌破**作为交易假设失效依据，不引用整段行情起涨低点；以关口下0.5%作为试运行风险缓冲参考。PULLBACK必须有当日真实回踩与反弹确认（MA20附近回踩低点在MA20下3%至上2%区间、当日收盘站回MA20、收盘强度≥55%、收盘高于前收且higher_low已核验），才使用**本次已确认的回踩日低点**下0.5%作为试运行失效参考。MA20、MA60、过去30日最低点、通用support_invalidation和远期启动低点均不得单独代替本次买点失效位。0.5%缓冲和回踩距离均为待回测研究假设。止损失效价必须低于本次入场下沿，否则买点证据不足，保持WAIT，禁止伪造价位或将一笔新建仓风险延伸到趋势起点。只有来源于已独立确认三级行业的个股才有机会进入READY；候选/观察行业在上游研究，不通过正式handoff；短线距离MA20超过8%、chase=high、正式风险大于6%或上方已知阻力不足1.5R均暂缓。READY需同时通过120～180日已确认历史阻力核验，上方有效阻力小于1.5R降为WAIT_RISK_REWARD。交易前需确定盘中与收盘触发方式，并考虑跳空/滑点，止损并非保证成交。
9. **唯一正式TOP1决策**由 [模型研究协议](TREND_BUY_MODEL_TOP1_RESEARCH.md) 定义。选择锁定后，仅对当选TOP1调用原 `evaluate_candidate`，按本协议第7–8步和第3节执行独立交易风控。非TOP1不计算交易计划；WAIT只观察，DROP/UNCERTAIN/弃权不递补。
10. 提交唯一当日 `research/trend_buy_company_reviews/latest.json`：原公司reviews字段、真实来源及日期完整覆盖程序候选，`as_of_date` 为参考交易日，`explicit_no_prior_formal_or_archive_input=true`；同文件 `top1_selection` 完整符合模型研究协议机器交接格式与当前 main 的 `scripts/research_model_top1.py` 契约，绑定实际冻结admission Git blob SHA。程序重放admission、核验研究范围及证据、锁定选择并执行独立风控。
11. 执行第7节唯一正式发布并核验真实成功；按第8节报告和前瞻验证。盘中不重新选股。

## 3. 状态含义
- READY：经证据核实，行业趋势确认且价格形态、合理区间、结构失效及风险全部就绪；仅下一交易日条件性入场，非无条件买单。
- WAIT：来自**已确认三级行业**、但个股本次未满足买点的研究结果；包括MA60下方的修复、启动未确认、分歧后的等待承接。正式handoff中WAIT必须清空可执行交易计划字段，改用独立watch_reference传递由独立TOP1风控计算的近端观察触发价/参考区间（可以为空）；远期突破高点不得冒充当前买点，观察参考位也不得冒充持仓止损。WAIT触及观察区不自动升级READY，不改变板块确认Gate，也不凭任何单一外部价格上涨信号执行买入；下一完整交易日重新计算和确认。
- UNCERTAIN：业务或关键结构缺失，不得补造数据。
- DROP：业务关联被证伪、重大硬风险或已验证结构失效；MA60和单日回落均不是充分淘汰理由。
- COOLING与正式WAIT是不同维度；暂停新建仓不直接命令已持有的用户止盈止损。持仓退出根据独立结构保护、业务逻辑证伪与风险预算执行。

## 4. 交易时间与异常
北京时间工作日19:00执行完整研究，使用当天已完成行情发布；非正式交易日不把过期数值当新信号。全局输入、数据日期、名单/来源契约、代码审计、GitHub提交或READBACK任何一项关键失败均BLOCKED，不写新正式结果或handoff。单个SW3研究证据不足按INCOMPLETE如实记录，不产出该组TOP1；全部组弃权时可发布完整审计及空handoff（不同于上游signals=[]时不发布）。**开盘前故障恢复：** `INCOMPLETE` 属于流程或证据未完成，不是有效弃权决策；允许在参考交易日收盘后、下一实际交易日北京时间09:30前补齐原始冻结TOP5同口径资金及研究证据，重新执行该组并正式成对发布结果和handoff。保持原名单、顺序和参考交易日，不读下一交易日行情或收益；仅重试未完成组，已有效完成的COMPLETE/NO_SELECTION组及其原始证据、选择、独立风控保持不变；不得因偏好或未来走势改选。新结果记录被替代的正式结果/handoff Git blob SHA、run_id、原因及恢复组，旧记录保留在Git历史。采集、正式发布前及推送前均校验窗口，09:30起禁止补写该交易日；交易日历无法核实则保守阻断。已完成的有效决策或相同结果不重复发布。连续多日行情指标只是形态代理，不证明实际资金身份，也尚未证明超额收益；生产参数须通过严格截至当日日K的历史回放验证。

## 5. 程序预筛与深研边界（唯一生效）

1. **输入**：只接收同日期已确认且直接受益的申万三级行业，验证冻结行业公司表、全部manifest和part、公司指数、财务来源哈希及已完成日K。硬过滤ST/退市、非正价格或MA20/MA60、缺少至少一项正值PE_TTM/动态PE/PB、缺少营收同比或归母净利润同比、以及营收同比<-20%且归母净利润同比<-50%的公司（两项恶化须同时成立）；单独低于MA60不是淘汰理由。有效K线不足65根、价格口径差异超过1.5%、未来数据，一律拒绝进入候选。
2. **统一入场优先竞争（`ENTRY_FIRST_NO_QUOTAS`），最多五席**：所有硬合格且具备有效65根以上同日历史K线的同业先计算10/20/60日同行相对收益分位和近10日上涨持续性，同时保留轻量入场结构证据。无任何预留领涨或入场席位；有同日核验入场机会代理的公司按入场位置分排序（同分再比较持续领涨分及代码），取最多5家。只有不足5家时，才从其他具备有效历史及财务证据的公司按持续领涨分依次补足，记为`WATCH_FALLBACK`。入场机会代理不能证明买点已确认，不能赋予READY。同行可比样本不足3家时阻断当行业分位推断。
3. **趋势持续性辅助分**：`continuity=0.40×20日分位+0.30×60日分位+0.20×10日分位+0.10×近10日上涨次数分位`；`leadership=0.80×continuity+0.20×fundamental`。该分数只在同入场分时排序，或入场资格不足时筛选观察补足，不为持续领涨股预留席位。
4. **统一优先筛选的入场位置分**：`entry=0.65×entry_reference+0.20×price_structure+0.15×fundamental`，仅对具备已验证轻量入场资格的公司进行统一竞争。财务基础分优先采用审计时点可验证的扣非净利润同比，缺失时按扣非EPS或归母同比回退；同时核对经营现金流、非经常性收益与估值。高同比不等同超市场预期。
5. **财务证据语义**：`financial_publication_date_verified=true`仅表明同一家公司的F10来源标识、财报期、公告日期、更新日期均经截至交易日校验；不代表所有财务值可靠或具有超预期表现。`source_financial_provenance_verified_count`是当日已完成该来源日期核验的公司数，财报核心指标是否可用另行标记。模型必须核实并区分证据缺口。
6. **模型深研**：按模型研究协议执行。
7. **发布**：按第7节执行。

## 6. Python资金冻结与产物核验

既有候选冻结工作流 `.github/workflows/prepare-trend-buy-candidates.yml` 在原TOP5生成后调用 `scripts/freeze_trend_buy_fund_flow.py`，资金不改变Python筛选和顺序。逐日资金、1/5/10/20日指标、来源、查询时点、整组备用尝试及失败原因写入同一 `research/trend_buy_candidates/latest.json#fund_flow`，随原名单一次提交及READBACK。初次发布及开盘前恢复INCOMPLETE组均核验同文件、同参考日资金快照及来源状态。

资金采集实现：既有候选冻结工作流在Python TOP5生成后调用 `scripts/freeze_trend_buy_fund_flow.py`。腾讯优先，读取历史逐日资金、当日资金汇总与带交易日时间戳的15:00分钟末记录，验证当日身份、收盘和资金分类一致；历史接口仅截至前一交易日时同源拼接当日记录，若当日已包含则核验一致后去重。东方财富直连为整组备用；任一候选核心数据不可验证，则整组尝试备用，仍失败则记录INCOMPLETE。金额分母使用经过日期及身份核验的实际不复权日成交额；行情分析仍以项目已有冻结行情为准，资金接口附带价格仅用于身份及异常检查。接口调用、失败原因、逐日金额和滚动指标随原名单一起冻结并由admission SHA绑定。模型不得补造缺失资金。

若无同日真实冻结产物，使用实际GitHub Actions候选冻结工作流运行并核验成功与main READBACK；仍无同日成功且含资金快照的真实产物则BLOCKED。组内核心当日及近5日数据必须真实、同源、可比；完整逐日序列及1/5/10/20日窗口按实际可验证数据留存，10/20日非关键缺项按UNKNOWN披露。单组资金INCOMPLETE不等于全局BLOCKED，按第4节及模型研究协议处理。禁止跨供应商拼接或用模型重新抓网页替代冻结资金。

## 7. 唯一正式发布与交接

唯一生产工作流 `.github/workflows/run-trend-buy-formal.yml` 调用 `build_trend_buy_manual_research.py --model-top1-research` 和 `run_model_top1_formal.py`；结果 `python_top5_by_industry` 保存原始名单及顺序，`model_top1_selection`保存证据，`top1_decisions`保存选择及风控。`top1_by_industry` 为每SW3已选且READY/WAIT的执行投影；历史归档字段 `top5_by_theme` 仅供切换日前归档的独立只读兼容与非生产研究，不作为任何正式结果或重新发布入口。`trend_buy_handoff.py` 只传已选TOP1的READY/WAIT，结果与handoff成对原子提交并READBACK，盘中不重新选股。

跟踪 `.github/workflows/run-trend-buy-formal.yml` 的实际Actions运行，核验真实成功、参考交易日及成对run_id、`selection_policy` 与当前main的 `scripts/run_model_top1_formal.py` 中 `POLICY` 常量一致（仅机器校验）、实际Git blob SHA及main READBACK。完整核验 `python_top5_by_industry`、`company_reviews`、`model_top1_selection`、`top1_decisions`、`top1_by_industry`；handoff代码必须恰好对应 `top1_decisions` 中READY/WAIT的TOP1。任一关键环节失败按第4节BLOCKED处理，不以历史或替代产物冒充当日成功。

## 8. 中文报告与前瞻验证

报告参考交易日、上游确认行业、原始Python TOP5（按 `python_top5_by_industry` 原序完整展示）、模型唯一TOP1或弃权及关键比较、最强反证和数据缺口；仅对当选TOP1报告Python交易状态、买点/失效/风险赔率或等待及不能执行的理由。执行投影只读 `top1_by_industry`；DROP/UNCERTAIN的选择及状态从 `top1_decisions` 与研究证据核验，不冒充执行投影。报告实际Actions、发布及READBACK证据或实际阻断原因；报告不展示非现行机会分。合法零信号按第2节报告。

规则锁定后连续前瞻验证10–20个交易日；只在本轮选择锁定并正式发布之后，检查已成熟历史信号未来1/3/5个交易日相对Python首位及TOP5均值、组内名次、前二命中、选择完成率及弃权率；实际成交与风险收益另列。缺失或未成熟明确标记，不删除失败样本、不事后改选、不用单日收益调整规则；验证不参与本轮选择。研究目标按模型研究协议，收益效果尚待验证。

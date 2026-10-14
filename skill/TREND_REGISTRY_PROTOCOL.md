# A股板块趋势榜｜正式研究与发布协议（精简版）

> **适用任务**：「A股板块趋势榜」北京时间工作日06:40、18:40。18:40首次发现阶段先读不包含历史入榜主题的 [TREND_DISCOVERY_NEUTRAL.md](TREND_DISCOVERY_NEUTRAL.md)；冻结模型首轮候选后，才加载本协议和完整历史趋势账本。06:40增量复核可直接读取本协议。
>
> **主线只有三步**：模型独立发现 → 全部历史趋势复核 → 合并判断、校验和发布。Python可以计算客观市场指标、校验状态与JSON，但**不再作为每日第二个趋势发现者**。保持正式趋势状态、资格、排序、数量、已有JSON schema与下游输入契约不变。

## 1. 执行模式和最短主流程

### 1.1 06:40｜早间增量复核

仅使用上一有效完整A股交易日**已正式提交并READBACK**的research/trend_registry.json及可核实的新隔夜事实；遵守原交易日、基线和日期Gate。保留原状态、原核验日期和历史证据，不将境外隔夜行情冒充当日A股收盘，不产生新的当日正式handoff。registry不存在、日期无效、结构不完整或为BOOTSTRAP_PARTIAL时报告REGISTRY_BASELINE_UNAVAILABLE，不用旧优先榜冒充正式基线。

### 1.2 18:40｜完整收盘研究

执行前先确认**真实A股交易日、正式收盘数据已经完整、交易日期和核心行情覆盖有效**；未通过则报告阻断，不宣称完成当日收盘研究。

1. **模型独立发现**：只加载中性发现规范；使用可核验的本日及必要历史原始行情、全行业客观统计和真实产业资料，从市场结构与政策/供需/订单/盈利两条线主动发现趋势。不读取昨日registry、handoff、历史精选主题、Python推荐候选/Top20及这些名单的转述；可以读取无推荐排序的全量客观指标，但不可把程序精选方向当作模型首发。形成一个**简洁、可核对**的首轮候选清单（主题、证据、日期、已核实行业、覆盖缺口），在读取旧榜前冻结于本轮研究记录；无候选也如实记录。**日常不要求额外Git预提交、额外READBACK或严格来源归因审计**，未做到外部隔离时不得声称VERIFIED_PRECOMMIT。
2. **历史全量复核**：此时才加载本协议，并读取上一成功正式registry，保留真实Git blob SHA、交易日与只读previous副本。逐一核对全部旧trends和recheck_queue的最新事实、原验证日期、第一锚、market_state、state_history及失效条件；包括高潮/衰退、待复核和已失效方向。**全面检查不等于每条重做深度研究**：没有重要新证据的主题记录简短HOLD和其原核验日期；出现重大变化、关键结构破坏、产业证伪、证据冲突或研究缺口时深入复核。历史断链才回看相应旧Git提交；禁止后来行情回填往日。首轮未命中某个旧主题不构成降级/删除依据。
3. **合并、校验和发布**：将首轮新发现与全部历史主题去重，独立评估产业/商品趋势、A股市场状态、真实受益映射及当期新仓/ETF机会；生成完整proposed registry和按旧资格/排序/数量生成的proposed handoff。使用真实冻结的previous/proposed及上一版blob SHA运行状态迁移Gate，并运行双文件一致性Gate。均真实PASS且原研究/行情/行业路由/数据Gate通过后，按第5节提交两份正式文件并逐一READBACK；失败准确报告，不发布伪成功的新榜。

**日常不再要求**：读取Python发现候选再做来源交叉归因、MODEL_ONLY/PYTHON_ONLY/BOTH逐条证明、额外首轮Git冻结提交、为不变化主题重写长篇研究、完整5/10/20日策略绩效回放。辅助脚本即使仍在现有上游流程生成候选，也**不参与本任务的正式趋势发现、状态判断或优先榜排序**；不必为删去这一研究步骤更改上游采集工作流。

## 2. 必须保留的趋势研究纪律

| 判断层 | 正式字段 | 独立证据与结论边界 |
| --- | --- | --- |
| 产业/商品第一锚 | trend_state（T0/T1/T2/待核验）；lifecycle_status（有效/待复核/已失效） | 供需、技术/政策落地、真实订单与盈利、国际商品等产业本身证据 |
| A股市场表现 | market_state（沿用现行枚举） | 同口径量价、上涨广度、相对强弱、龙头/中票扩散、承接、此前确认的价格结构 |
| A股实际映射 | industry_codes / industry_names、研究证据 | 上下游成本、主营业务、利润传导、申万三级行业真实归属 |
| 新仓优先资格 | in_new_position_priority、handoff | 沿用原新仓资格、风险、ETF时机、排序、数量标准 |

**三种情况要分开处理：**

- **普通波动**：单日调整、局部分歧、某只龙头走弱或资金流出，不自动升降级；若核心证据仍成立，HOLD并记录风险。不能把“旧状态未被新事实推翻”冒充“今天已重新确认所有事实”。
- **A股真实退潮**：可比多日结构恶化并有独立反证时下调market_state；若**同日客观数据**表明主要股票普遍大跌、核心与中票同步恶化、事先形成的关键支撑已破位，可按第4节紧急通道当天降级，**不机械等次日**。即使板块比暴跌的大盘相对抗跌，其自身结构仍可能失效；真实相对强弱必须如实记录。
- **产业关键驱动证伪或恢复**：产业T等级和lifecycle_status的下降，必须有商品/政策/订单/供需/盈利等**产业自身**新反证，不能只因A股板块下跌而标产业失效。升级、失效后恢复也不能只凭单日反弹，要满足原独立确认条件。

退出新仓榜不等于产业失效；A股market_state=失效不自动等于lifecycle_status=已失效；映射不足不等于产业不存在。原有历史状态必须忠实保存，实际新状态变化须写真实原因和日期。

**商品及跨市场**：黄金、原油、铜等主题要分别确认国际第一锚、A股受益公司的真实利润传导和本地行情，不把同涨当成直接受益。国际报价注明时区、现货/合约性质和是否最终收盘。数据及研究资源充足时，可附5/10个相关市场交易日的条件性情景、反证和到期回验；**前瞻/回验是辅助研究，不是当日正式发布的新增硬Gate**，也不能直接决定当日状态。资金流向同样仅可作注明窗口、口径及日期的辅助证据，不能单独改变状态或排名。

## 3. 数据输入与研究分工

**模型负责研究，不要求模型重复计算数千只股票的行情。** 使用已经生成且日期一致的全市场客观数据、行业量价统计与个股结构作为事实输入；Python负责统计和核验，而非提供必须逐一审阅的“推荐趋势名单”。

- 可以使用data/latest.json、data/shards中的原始行情及data/research/sector_discovery_audit.json里**真实行业总体指标**（涨跌、广度、量比、相对强弱、样本覆盖等）；读取前核对trade_date、样本和口径。**不能把audit文件里的排名或程序精选候选当成独立发现**。对于历史主题可读取与之对应的有日期的客观数据和已核实行业路线。
- data/research/sector_discovery_snapshot.json的model_research_candidates、deferred_candidates、程序STRONG/EMERGING评分，以及theme_evidence_snapshot.json的research_candidates、tracked_theme_alerts，**不再是18:40模型研究的必读资料或入榜依据**。这些文件既有产出可保留，但不应因候选数、TopN或程序状态阻断本任务；不能宣称已完成实际没有覆盖的概念市场扫描。旧“发现来源”标签只按真实已知历史保留，不要求每日补齐或追认来源。
- research/theme_industry_catalog.json只作为可核验的主题与申万三级行业研究映射；core和related角色不能混同，同主题公司避免重复计数。公司业务、业务分部与真实利润传导须独立核实，不能因为目录收录就认定受益。目录、分类行业数量按当期版本核验，**不固定331个行业**；实际样本/概念覆盖不足就记录缺口，不把不完整写成全覆盖。
- 全市场基础覆盖可由程序客观统计保障；模型无需每天为全部行业逐一写产业报告，只需主动检视全市场结构及新信息，再对值得研究的候选和旧主题关键变化核验来源。某一辅助行情统计不可用可记未核实，不自动阻断其他合格方向；但若核心交易日、价格真实性、必要行业覆盖或实际结构证据不成立，不能宣称正式研究Gate通过。

**日常留痕只要够用**：本轮研究记录简要保留独立首轮候选及来源/截止日、扫描范围与局限、旧主题HOLD/CHANGE及关键证据、程序Gate结果。现存scan_audit.discovery_attribution等历史字段不删改；新轮不强制MODEL_ONLY/PYTHON_ONLY/BOTH、pre_history_scan、预先Git提交、额外归因校验。辅助程序的技术功能是否保留不等于让其重新进入模型趋势发现流程。

## 4. 历史连续性与状态迁移Gate

### 4.1 Registry仍是完整账本

research/trend_registry.json（schema_version=1，result_kind=a_share_trend_registry，status=COMPLETE，timezone=Asia/Shanghai）要保存**全部**历史追踪主题，包括本轮新发现、旧主题延续、高潮/衰退、待复核与失效记录；保留invalidated_history、recheck_queue和既有scan_audit字段。每条趋势保留trend_name、trend_state、market_state、lifecycle_status、first_seen_trade_date、last_verified_trade_date、industry_codes/industry_names、in_new_position_priority、supporting_evidence、contrary_evidence、invalidation_condition、change_reason及state_history。证据注明来源和日期。

上一版旧主题的**first_seen_trade_date不变，state_history必须原样作前缀，仅追加当轮事件**；不得因改名、拆合或退出榜单在现行按trend_name审计的程序中静默删除旧趋势；真正需要身份迁移时先通过版本化程序与测试。历史初始BOOTSTRAP_PARTIAL不是COMPLETE；脚本要求正式前后均为COMPLETE，不能修改状态字符串骗过Gate。缺失历史用待复核记录说明，不能凭后续新闻补造往日历史。

### 4.2 每条旧主题都进行轻量结构化审计

在proposed registry的scan_audit.state_migration_gate中写入mode=full_close、previous_registry_trade_date、previous_registry_blob_sha（真实Git blob SHA）和current_trade_date。对上轮**所有trends**各有一条reviews（HOLD/CHANGE），说明前后market_state、trend_state、原因及必要evidence；产业或市场/lifecycle变化，按现行脚本追加准确state_history。**不变主题仍需一条审核记录，但允许简短理由，不强制每日重复外部深度搜索。**

evidence如参与迁移，使用现行dimension、direction、impact、trade_date、source、finding，必要的多日结构记录window_trading_days；状态变更必须有晚于上一基线交易日的真实新证据。技术校验只能验证形式、日期和条件组合，**不能替模型证明外部新闻或行情事实必真**。任何状态变化不能用模型自填的CRITICAL、虚构旧支撑或不可核验来源代替证据。

### 4.3 当日集体退潮快速通道（仅市场状态）

仅有**同日完整收盘**、有效行业数据及事前已存在的关键支撑水平时才使用。按现行scripts/validate_trend_state_migrations.py及对应测试审查；在对应review中提供same_day_collective_breakdown（trade_date、support_breaks，其中含industry_code、早于今日的reference_trade_date、support_level、observed_close、source），并提供MARKET_STRUCTURE、MARKET_BREADTH、RELATIVE_STRENGTH的真实调查结果。此通道实际运行需传同日完整data/research/sector_discovery_audit.json作为--sector-audit；它只是**可验证的A股market_state下降路径**，不自动降低产业T等级或宣布生命周期失效。行业数量动态核实，程序门槛是质量限制而非已验证盈利阈值。若快速通道证据不全，可按其他已有真实反证研究，不能伪造PASS。

对于旧账本中产业已失效但缺少结构化产业第一锚反证的记录，可参考research/audits/2026-10-13_lifecycle_semantics.json只读核验；不要每日完整重跑历史语义审计，更不得倒改历史失效事件。新事实足以迁移才当轮追加记录。

## 5. 发布校验、GitHub落库及报告

### 5.1 正式文件与现行程序

- research/trend_registry.json：**完整趋势生命周期账本**，不受当期Top3或其他数量限制。
- research/trend_handoff.json：**仅原规则合格的当期新仓优先方向**，沿用原schema、signals、排序、数量、行业代码、映射/消费者契约，不新增历史衰退主题给下游买点榜和盘中监测。
- scripts/validate_trend_state_migrations.py：现行历史迁移及反证Gate。
- scripts/validate_trend_publication_pair.py：新一轮**完整proposed registry + handoff草稿**交易日期、资格顺序、状态及路由一致性Gate。其--historical-baseline-only仅用于旧数据回放，**不得在正式新发布时使用**。
- 既有行情质量、正式交易日、行业路由、完整研究和JSON校验要求仍生效；不要为了减少耗时绕过必要PASS。

用真实本轮临时文件先执行（具体CLI版本以仓库现行脚本为准）：

~~~bash
python scripts/validate_trend_state_migrations.py \
  --previous /tmp/previous_registry.json \
  --proposed /tmp/proposed_registry.json \
  --previous-blob-sha <实际冻结的上一版registry_Git_blob_SHA>
# 仅在同日真实集体退潮通道时追加 --sector-audit <同日有效文件>

python scripts/validate_trend_publication_pair.py \
  --registry /tmp/proposed_registry.json \
  --handoff /tmp/proposed_handoff.json
~~~

上述两个程序都必须**真实退出码0且返回status=PASS**。若当前运行环境无CLI执行能力，要准确报告Gate无法执行和正式发布被阻断，不能以“手工检查通过”代替。不同辅助快照是否可用不替代以上Gate。

### 5.2 提交及READBACK

预校验通过后，优先使用**已验证可靠**的原子双文件提交；若运行工具不具备安全原子提交能力，仍使用原来的先提交registry、重新FETCH/解析/READBACK确认交易日期、内容及commit/blob SHA，再提交**已经预校验的**handoff并再次READBACK的流程。两份文件要相同trade_date，handoff signals与registry当轮in_new_position_priority主题的名称、顺序、状态与路由完全一致。

一旦出现研究/行情不足、STATE_MIGRATION_GATE_BLOCKED、PUBLICATION_PAIR_GATE_BLOCKED、REGISTRY_WRITE_FAILED、REGISTRY_READBACK_FAILED或下游handoff写入/回读失败，报告实际已成功步骤及**未完成的正式发布部分**，不把草稿、旧榜或只提交成功的一份宣称为本日完整完成，不绕过安全拒绝或强制覆盖Git版本。19:00买点榜属于独立任务，本任务不可谎称已触发它；下游只能使用**已成功完成**的当日正式handoff。

### 5.3 中文结果与非关键研究分流

日常报告只保留**完整趋势池（每条简要判断）→当期新仓优先榜→重大新发现/旧趋势变化及失效条件→产业与A股市场背离/ETF参与风险→研究缺口→实际GitHub Gate/READBACK结果**。重要主题可详述，其余保持简洁。可靠资金观察及商品5/10日展望在材料可得时附注，不因缺少预测或回验阻断合法正式发布。

**长期策略效果验证不放入18:40关键路径**：可使用既有research/audits历史归档及冻结Git SHA在独立研究或以后单独任务评价5/10/20个交易日表现、趋势过早退出和失效识别滞后；不修改旧结论，不凭单次结果临时改验证阈值。本次精简不创建新的日程或另一个生产榜单。

## 6. 每轮检查清单

- [ ] 06:40只增量；18:40交易日及收盘数据Gate有效。
- [ ] 模型先从中性事实自主发现候选并记录，**没有先读旧趋势榜或Python精选候选**。
- [ ] 随后完整复核所有历史趋势，HOLD可简写、变化需深查、旧历史只追加。
- [ ] 产业第一锚、A股市场、真实映射、新仓资格分别判断；真实结构破位及时处理。
- [ ] Python只承担客观量价计算与必要Gate，**不再强制Python趋势发现、交叉归因或额外首轮Git冻结**。
- [ ] 真实previous/proposed及Git SHA进入迁移Gate；正式registry/handoff草稿通过pair Gate。
- [ ] 两份正式结果都实际提交并逐项READBACK，失败如实报告。

**维护规则**：只有独立发现、历史复核、校验发布三项正式研究步骤。新建议先判断是否真正影响当日结果；不影响的历史回放、发现算法比较、长篇展望与辅助统计放在主流程外，不再继续叠加到定时任务Prompt。

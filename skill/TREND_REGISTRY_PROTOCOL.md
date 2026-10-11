# A股板块趋势榜｜完整趋势状态协议（增量扩展）

> 本文件为“A股板块趋势榜”保留跨轮完整趋势状态管理，并补充仅供观察的资金流向与量价配合证据。既有产业 T0/T1/T2 判定、市场状态判断与迁移条件、全行业扫描、早间增量复核、ETF 时机、新仓优先榜资格/排序/数量、行业路由及写入审计均保持原逻辑。本文件不得作为趋势买点榜或盘中监测的新输入。

## 1. 两份输出与职责边界

- `research/trend_registry.json`：完整趋势状态账本，仅供下一轮**趋势榜**复核；保存新仓优先榜以内、以外的全部已发现且未证实失效的趋势，以及待复核的历史趋势。不能仅根据当期优先榜反推完整趋势池。
- `research/trend_handoff.json`：原格式、原排序、原生成资格，**仅当期新仓优先榜**；供趋势买点榜及其下游盘中快照继续使用。不得混入高潮/衰退但不适合新仓的其他方向，也不得扩展 schema/更改消费者。
- “退出新仓优先榜”与“趋势失效”是不同事件；前者不可自动触发后者。
- 盘中快照由当期 `research/trend_handoff.json` 与 `research/trend_buy_handoff.json` 中冻结的行业和公司名单生成；`research/trend_registry.json` 用于趋势研究记录，不直接扩充盘中监测股票池。

## 2. 读取与事实优先级

每轮趋势榜在原有交易日、日期/模式 Gate 之后，读取 main 的 `research/trend_registry.json`、`research/trend_handoff.json`（需要时）以及原有数据/行业路由文件；记录最新文件 blob SHA。registry 仅提供**历史待复核对象、上期记录与状态转换线索**，不能直接证明当期状态、维持资格或代表今日行情，也不得反向取代当前商品、订单、产业、板块行情与正式全市场扫描。

18:40 完整收盘版仍须从**全行业/主要概念板块的全量扫描**开始，独立核验所有上期 registry 中尚未证实失效/待复核的方向，并扫描新增异动。逐一记录保留、状态转换、待复核或已证实失效的证据，不能只审当期 Top 2–3，也不能把 registry 读入视作完成全量扫描。过去状态只有新证据满足原任务已定义的确认/失效标准才能变化；没有足够新证据时标记“待复核”，原记录及其原始日期保留，不宣称昨天结论今天仍成立。明确失效者保留历史记录而不继续列为有效趋势。

06:40 早间增量版延续原有 previous_trade_date 与隔夜证据规则；只能从同一 previous_trade_date 已完成、已成功提交及 READBACK 的正式 registry 基线做增量复核。隔夜证据不足时状态不迁移，不做全市场收盘版伪重算。若 registry 缺失、日期不匹配、结构无效或为 BOOTSTRAP_PARTIAL，标记 REGISTRY_BASELINE_UNAVAILABLE，不把历史资料当正式基线；在下一次有效 18:40 完整版进行首轮正式全量重建。原有交易日与 handoff Gate 仍必须遵守。

## 3. 正式 registry 数据契约

正式版顶层字段：
- `schema_version=1`, `result_kind=a_share_trend_registry`, `trade_date`, `generated_at`, `timezone=Asia/Shanghai`, `status=COMPLETE`；
- `scan_audit` 至少包含：`full_market_scan_completed`, `previous_registry_trade_date`, `previous_trend_count`, `previous_trend_rechecked_count`, `new_trend_count`, `pending_revalidation_count`, `invalidated_count`, `new_position_count`, `evidence_cutoff_trade_date`。06:40 增量版额外注明模式，不能宣称进行当日全量收盘扫描；
- `trends`：完整趋势/待复核记录集合，稳定主题身份不得因为改名或退出新仓榜重复造身份；每条至少有 `trend_name`, `trend_state`(T0/T1/T2/待核验), `market_state`, `lifecycle_status`(有效/待复核/已失效), `first_seen_trade_date`, `last_verified_trade_date`, `industry_codes`, `industry_names`, `in_new_position_priority`, `supporting_evidence`, `contrary_evidence`, `invalidation_condition`, `change_reason`, `state_history`。证据每项注明来源和日期；历史事件包括原状态、目标状态、日期和原因。待复核历史项必须保留其 last_known_* 原始日期，不得谎称现状；
- `invalidated_history`：保留当轮及历史已验证失效的主题与失效证据/日期，禁止无记录删除；
- `recheck_queue`：针对不能由可靠文件恢复具体历史状态的旧主题，明确标记 provenance/unknown，待下次全市场扫描单独核验，不占用新仓名额。

如果字段名未来要调整，须同步升级 schema 与本协议；不允许静默混用或输出省略号。不得把历史 `高潮/衰退` 自动当成当日结论。完整账本指覆盖本轮能识别的全部现存趋势及未解决历史主题，并不声称从 2026-09-17 之前恢复了不存在的历史资料。

## 4. 初始化与兼容

初始 `trend_registry.json` 如为 `status=BOOTSTRAP_PARTIAL`，只是从已验证文件恢复的**待核验历史线索**，不是已完成的当日完整趋势分析。首次后续有效 18:40 正式运行必须完整扫市场，复核全部现存 bootstrap 条目及 recheck_queue 后才可写 `status=COMPLETE`；旧方向没找到足够当期证据时仍存为“待复核”，不能默默清空，也不得假定有效或失效。

先完成本轮全部研究，构造并校验完整 registry（包括全部旧方向去向），再依据原逻辑生成仅含新仓优先方向的 handoff。正式 handoff **必须继续保持原有 schema 和字段顺序/含义**，不添加任何旧趋势。仅用 handoff 作趋势买点榜及盘中监测输入；不得改变任何下游任务、工作流或文件的读取契约。

## 5. 一致性、提交与失败处理

只有本轮独立研究、数据/覆盖 Gate 与 registry schema/覆盖/状态迁移审计均通过才允许正式落库；先取得 main 的目标文件最新 SHA，JSON.stringify 后再 JSON.parse 验证同一完整 UTF-8 内容。先正常提交 registry，取得新 commit/content SHA，立即重新 fetch + 完整解析并核验日期、主题去重/覆盖、状态转移与新 SHA；只有成功后才能按原任务写 `trend_handoff.json` 并 READBACK。hand-off 的 signals 必须与 registry 同轮 `in_new_position_priority=true` 主题**名称和顺序一致**，但格式必须是原有的简化格式。

任何无法验证的正式全扫、registry 写入失败或 READBACK 不符均报告 REGISTRY_INCOMPLETE/REGISTRY_WRITE_FAILED/REGISTRY_READBACK_FAILED；本轮不得发布一份号称成功的新 handoff，不把未落库内容当已持久化历史。保留原有预写 JSON 验证、错误分类、最小审计和安全检查要求；不要为了完成 registry 绕过拒绝或更换写入通道。

写入结果向用户同时展示“完整趋势池（含高潮/衰退及待核验）”“当期新仓优先榜”以及所有旧趋势的状态变化/退出原因。完整趋势池不设 2–3 名上限；只有新仓优先榜沿用原数量选择逻辑。

## 6. 资金流向与量价配合｜仅作辅助观察，不改原判定

**职责与优先级**：保持原有“产业 T0/T1/T2 × 市场趋势”独立研究、确认/失效标准及全市场扫描顺序完全不变。在按原规则形成板块的市场结构判断后，若有可比且可核验的数据，再补充资金流向与量价配合观察。资金既不构成新的入榜/出榜 Gate，也不单独触发市场状态迁移、T0/T1/T2 调整、趋势失效、ETF 时机、当期新仓资格或排序；不得按净流入绝对金额重新排行。原有相对强度、板块广度、成交、龙头/中票扩散、分歧承接的判定优先。

**观察内容**（同一板块、同一统计口径，优先当日/近5交易日/近20交易日；这些窗口彼此重叠，不可当成三组独立证据）：
- 净流入/净流出方向与金额、可取得时的区间内流入/流出天数；有成交额时观察净流量相对区间成交额的占比，避免不同规模板块只比绝对金额；
- 与各窗口对应的板块价格涨跌、成交量/成交额变化，及原市场链已经核验的相对强度、广度和分歧承接；成交放大本身不能证明净流入；
- 对于“当日资金显著流入，但20日累计净流入较小或为净流出”等情况，检查口径及窗口包含关系，描述为“短期转向待确认”，不得写成“连续20日流入”；同理，单日流出不等同于趋势结束。

**解读与展示**：只使用描述性观察标签“资金与量价相互印证”“资金与价格背离”“短期转向待确认”“暂无明确增量信号”“数据不可用/不可比”。持续净流入与价格、成交和广度同向，可作为已有市场趋势的辅助支持；持续净流出并伴随价格/广度走弱，可作为需要独立复核的反向线索；上涨伴随净流出、净流入伴随滞涨、下跌伴随净流入等背离应如实呈现，不预设为吸筹/出货，也不得单凭资金给出新的状态结论。资金流量是行情数据商依据成交单特征估算的统计指标，不等于可核验的机构仓位变化。

**数据质量与时点**：优先使用明确标注统计方法、板块成分口径、区间和截至交易日的同源数据；不同平台、不同板块分类及可能重复计算的数据不得直接求和或比较。06:40 隔夜版仅能采用符合原 Gate 的上一已完成正式交易日数据，不将盘中/旧数据伪称当日完整数据；18:40 正式版只将已经完整收盘且交易日匹配的数据描述为当日数据。缺少数据、来源日期不一致、统计口径不能对齐时记录不可用/不可比，不臆测、补造或因此阻断原有趋势研究与发布。

**落库与兼容**：不增加 trend_handoff.json 字段、不修改 schema_version、不改变下游输入。若本轮能取得可比资金证据，仅在 trend_registry.json 已有每条趋势的 supporting_evidence / contrary_evidence 中，以注明来源、截至交易日、观察窗口和“仅资金辅助观察”的描述性证据保存；中性、背离及不可用情况可在当轮用户报告中说明，不强制新增 registry 字段或要求为每条趋势取得资金数据。上述资金备注不是新的状态迁移依据；新证据不充分时仍遵守原来的待复核和状态迁移规则。

**本轮输出**：在原有“完整趋势池 → 当期新仓优先榜 → ETF时机/失效条件 → 旧趋势状态变化 → 持久化结果”的报告结构内，为有可靠数据的板块附一行“资金流向/量价配合观察”，标明具体窗口、方向和背离（如有）；无数据时标“未验证”，不因资金缺失删减原榜。


## 7. 程序化板块发现（V2 接入，保持原确认门槛）

- 18:40 的新方向研究须优先读取同一完整收盘交易日的 `data/research/sector_discovery_snapshot.json`；核验 `schema_version=1`、`result_kind=sector_discovery_snapshot`、`trade_date`、`no_trade_signal=true`、`scan_audit` 和 `audit_path`。对应 `data/research/sector_discovery_audit.json` 应具有同日来源、行业/概念覆盖及全部候选的可追溯筛选理由。文件不存在、过期或不一致时标记 `DISCOVERY_UNAVAILABLE`，不可把未验证的程序扫描写成已完成。
- 程序只负责根据客观量价形成强势（STRONG）与启动（EMERGING）候选，不得机械决定 T0/T1/T2、候选/确认、ETF 时机、新仓优先或交易动作。市场与产业状态仍由模型依本协议的现有证据规则独立判断。
- 程序前置研究名额仅约束**新增候选深研**；`deferred_candidates` 为容量不足待研究，不等于未形成趋势。所有历史已识别主题仍需逐项复核且不占这一上限。对于候选重叠须核对真实产业传导，不将同一股票集合因主题命名差异重复晋级。
- `status=INDUSTRY_ONLY_PARTIAL` 仅表示**申万行业量化扫描有效、跨行业概念成分覆盖未验证**。这种情况下可使用可靠的行业候选，但仍需独立补充概念领域的新异动调查，报告概念数据缺口；不能声称由程序完成全概念扫描，亦不能基于空缺认定粮食等跨行业主题没有异动。概念成分必须具备核验来源、历史生效日期，禁止回测时使用未来成分。
- 程序筛选失败与模型证据不足是不同状态：`NO_COHERENT_TRIGGER`、`LOW_SAMPLE_OBSERVE`、`INSUFFICIENT_COVERAGE`、`CAPACITY_DEFERRED`、`OVERLAPPING_CANDIDATE` 均留在发现审计；模型否决应在报告或当轮审计中说明独立事实理由。低样本行业不能因数值上涨就自动断定板块广度可靠。
- 现有 `research/trend_registry.json` 与 `research/trend_handoff.json` 的生产责任不变。registry 的 `scan_audit` 增记 discovery 的交易日、程序来源、候选数量、延迟研究数量、完整/部分覆盖及本轮研究去向；`full_market_scan_completed=true` 只可在实际完成全行业和主要概念调查的情况下声明。handoff 只保留通过原资格 Gate 的当期新仓方向，不扩展 schema；趋势买点榜和盘中监测不得直接消费 discovery。
- 数据生产步骤与模型研究执行顺序须保证已完成交易日数据、当日 discovery 提交与读取一致。文件无效或概念数据缺失时真实报告缺口；不使用历史/未来数据补齐，不因研究结论回填量化输入。
- 程序阈值（初版）为发现线索的**待回测参数**，绝不构成交易系统收益承诺或确认门槛。首次部署应先影子记录并测试历史样本；历史概念成分不可追溯时不可声称已验证跨行业回测。不得为了补捕某一个涨停案例调整已确定的市场状态晋级标准。

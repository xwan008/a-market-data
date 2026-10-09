# A股低风险买点榜｜价格区间与榜单输出 Override

本文件只覆盖 `RUNTIME_READ_PROTOCOL.md` / `SKILL.md` / `PRE_SCREEN_RESEARCH_SCOPE_OVERRIDE.md` 中关于正式榜单价格区间完整性、最终状态归类和用户可见输出的冲突规则。其他路由、预筛、Transmission、Expectation、Risk–Reward 规则保持不变。

## 1. 核心目标

正式“A股低风险买点榜”必须是可直接使用的价格榜单，而不是只给状态标签。

凡进入正式 `READY` 或 `WAIT` 榜单的公司，必须同时给出：

- `current_price`
- `reasonable_price_range`
- `low_risk_buy_range`
- `wait_reason`（WAIT 必须是合法原因枚举；READY 为 null）
- `wait_reason_detail`（可选的自然语言解释）
- `price_range_basis`
- `reentry_trigger`

其中 `reasonable_price_range` 与 `low_risk_buy_range` 禁止写 `N/A`、`待估值`、`待确认`、空字符串或 null。

## 2. 价格区间定义

### 合理买入区

`reasonable_price_range`：在未来 1–2 个季度重点观察窗口与可辩护的正常化盈利假设下，使用保守估值并预留基本不确定性后，仍具备可接受风险收益比的价格区间。

### 低风险买入区

`low_risk_buy_range`：在合理买入区基础上进一步加入更严格安全边际、下行锚和事件风险折价后的价格区间。正常情况下应低于或不高于合理买入区。

价格区间必须优先综合：

1. 未来 1–2 季度前瞻观察与可辩护的正常化盈利；已核实的较长期订单不因缺少精确季度兑现预测而被 Transmission 否决，但估值仍须保守处理兑现时点、利润率与收入确认的不确定性；
2. 保守估值倍数或可辩护的历史/同业估值区间；
3. 当前 60 日价格结构、主要支撑/成交密集区；
4. 主要风险事件的折价要求；
5. 至少 15% 左右保守上行空间作为低风险候选的重要参考，而非机械硬公式。

不得仅按技术支撑位生成“合理价值区”，也不得只按历史 PE 分位机械外推。

## 3. 无法可靠估值时的状态

若进入 Risk–Reward 后仍无法可靠给出 `reasonable_price_range` 或 `low_risk_buy_range`，则该公司：

- 不得保留在 `READY`；
- 不得保留在 `WAIT`（无论其 `wait_reason` 为何）；
- 必须转入 `UNCERTAIN`；
- `uncertain_stage` 记为 `RISK_REWARD` 或更准确的冲突阶段；
- `reason` 必须明确说明为什么正常化盈利、保守估值或安全边际无法建立。

因此，正式榜单中不允许存在“状态是 WAIT，但买入区间是 N/A”的记录。

## 4. WAIT 的含义

只有 Transmission=`SUPPORTED` 且已经完成价格区间计算、但当前价格或催化条件尚未满足时，才允许使用 WAIT。Transmission=`EARLY_EVIDENCE` 不得进入 WAIT。统一输出 `status: "WAIT"`，下列标签仅能写入 `wait_reason`，绝不作为 `status`：

- `WAIT_PRICE`：价格仍高于合理/低风险区；
- `WAIT_MARGIN`：已有可辩护价格区间，但当前安全边际不足；
- `WAIT_CATALYST`：已有可辩护价格区间，但仍需订单、利润、产能或客户验证等催化确认；
- `WAIT_EXPECTATION`：已有可辩护价格区间，但当前预期已较充分计价，需要新的预期重置或价格回到对应区间。

WAIT 必须同时保存明确的 `reentry_trigger`。自然语言等待说明写在 `wait_reason_detail`，不可覆盖枚举字段 `wait_reason`；READY 保存 `status: "READY"` 且 `wait_reason: null`。正式榜和 `research/low_risk_handoff.json` 必须原样保持相同的主状态与等待原因，禁止写入 `WAIT_*` 作为主状态。

## 5. Coverage

正式版新增：

```text
price_range_coverage = COMPLETE
```

满足条件：

```text
all READY + WAIT
必须先满足：status 只可能是 READY 或 WAIT；WAIT 的 wait_reason 属于合法枚举；READY 的 wait_reason 为 null。
然后都具有：
current_price
reasonable_price_range
low_risk_buy_range
price_range_basis
reentry_trigger
```

只有同时满足：

```text
materialized_view_gate = PASSED
trend_handoff_gate = PASSED
routing_coverage = COMPLETE
pre_screen_coverage = COMPLETE
transmission_coverage = COMPLETE
expectation_coverage = COMPLETE
risk_reward_coverage = COMPLETE
price_range_coverage = COMPLETE
publication_ready = true
```

才允许覆盖 `research/latest_formal_result.json`。发布前校验 `ready`、`wait` 两个数组中的每个条目均满足上述状态契约；生成低风险 handoff 时逐项复制其 `status` 与 `wait_reason`，核对公司代码、rank 和条目数量完全一致，不得静默丢弃不认识的状态。

## 6. 用户可见榜单

每次 19:00 正式版或手动正式执行，最终必须优先输出主榜单，至少包含：

| 公司 | 方向 | 当前价 | 合理买入价位 | 低风险买入价位 | 状态 | 等待/触发条件 |
|---|---|---:|---:|---:|---|---|

展示顺序：

1. READY；
2. WAIT；
3. 如无 READY，明确写“本轮无 READY”，但仍完整展示 WAIT 榜单；
4. UNCERTAIN / DROP / PRE_SCREENED_OUT 只做简短附表或数量摘要，不得喧宾夺主。

### 6.1 仅在全 WAIT 时增加「当前最值得考虑买入的个股」附表

**定位与触发条件（仅用户可见展示）：** 仅在本轮合法结果满足 `ready.length === 0 && wait.length > 0` 时，于**完整原 READY/WAIT 主榜之后、原分板块研究去向之前**，额外展示标题为 **「当前最值得考虑买入的个股」** 的独立附表。19:00 正式版、手动正式版依据本轮通过全部原有发布 Gate 的正式结果；07:00 早间增量版仅在其正式基线合法、且本轮增量复核结果可以合法展示时判断触发。任一 READY 存在、WAIT 为空、数据/基线不合规或发布失败时，均不触发；绝不拿上一轮榜单冒充本轮。

**候选范围与板块去重：** 只从本轮原正式 `wait` 中选择已通过 Transmission=SUPPORTED、估值与价格区间 Gate 的公司。按 `trend_handoff.signals` 中的趋势主题分组，而不是把每个申万三级行业都作为独立板块：例如动力煤、焦煤合并为「煤炭」，**同一板块最多一只，可为零只**。公司若归属多个趋势，只在优先级最高且业务关联已核实的板块出现一次；映射不明不得猜测。主榜原顺序、覆盖数与所有公司状态不受此附表影响。

**核心目标从“相对值得研究”切换为“当前价格是否值得参与”：** 不沿用原有 `risk_reward_ratio`、原榜 `rank`、距离原低风险买入区的远近或短期涨幅来直接决定附表首选。这些原始指标仍不变，但不能替代趋势交易的**入场价格—结构止损—合理目标**评估。股价不在原 `low_risk_buy_range` 内，不自动丧失附表资格；反过来，趋势最强、涨幅最大、甚至涨停，也绝不是优先入选理由。此附表属于独立的短中期趋势交易机会观察，不是原低风险价值买点 READY 的另一种写法。

**逐公司满足以下全部买入资格后，才有资格争夺板块唯一名额：**
1. **驱动有效：** 本轮趋势及公司级可归因商业传导仍有有效证据；市场预期未被明确证据证明已严重透支。若 Expectation=PRICED_IN/EXHAUSTED，只有本轮已核实的独立新驱动或预期重置且可解释尚存上行空间时才允许继续；已知趋势失效、盈利逻辑被反证的公司直接排除。
2. **当前可执行的入场机会：** 基于本轮已有、已核验的收盘价格与价格/成交结构，找到**现价附近**可执行的计划入场区或明确、近期可验证的入场触发条件；不得把必须远幅回调才能成立的低风险区直接称为“当前可买”。涨停、连续急涨、偏离有效支撑过远、波动/跳空显著扩大时，必须审查实际成交可行性与追高损失；若无法建立合理的现价附近入场与控制风险方案，则本轮不入选，不能单凭强势排第一。
3. **清晰的交易止损与目标：** 计划止损必须依据邻近、有效且可核验的技术结构/支撑失效点，留有合理波动缓冲；不能直接将原研究的长期估值/趋势失效价、极远低风险区下沿或任意固定百分比冒充短中期交易止损。目标价必须有现存压力区、价格结构或保守、可辩护的盈利/估值路径作为依据；不得为了制造漂亮盈亏比任意拔高。
4. **按可成交计划测算风险收益：** `潜在盈亏比 = (合理目标价 - 计划入场价) / (计划入场价 - 交易止损价)`，目标价 > 入场价 > 止损价，且以**计划买入区上沿**及保守目标检验，原则上要求 >= 2；同时检查预期波动、跳空和交易成本是否使止损不可控。计算不成立、价格结构/目标缺乏验证或交易风险无法约束时，不准为凑数而入选。

**板块内排序与空缺：** 先严格淘汰不符合上述资格的 WAIT 公司，再从剩余公司中优先选择**当前保守潜在盈亏比更好、入场和止损更有证据、交易可执行性更高**的一只；差异不足以证明高下时明确记录局限，不依赖原榜名次强行决胜。没有任何公司通过时，板块展示「当前暂无合适买入候选」和一个最关键原因；即使全部板块为空，也照常展示该表及无候选说明，不虚构至少一只。

**附表内容与状态边界：** 表格至少列示「趋势板块｜公司｜本轮收盘价｜计划入场价区/触发条件｜交易止损位｜保守目标价｜潜在盈亏比｜当前买入判断及原因」；若该板块无通过者，显示「暂无合适候选」及原因，不编造价格。必须标明交易日、已核实的依据及「附表为条件性趋势交易候选，非原榜 READY，仍为 WAIT；下一交易日若跳空/价格偏离预定入场区，应取消原买入判断并重新复核」。原 `reasonable_price_range` / `low_risk_buy_range` 依旧由完整主榜原样展示，不得被附表中的短期入场价、交易止损或目标价覆盖。

**仅展示、严格无副作用：** 附表只基于本轮合法执行过程中**已经取得且已验证**的公司与市场事实进行独立展示层计算，不追加 Universe 扫描，不更改或重复执行原选股、估值、风控和发布决策；不从冻结后禁止重读的 index/manifest/part/shard/legacy 文件取数，也不为填缺口而自行抓取未验证的行情。若现有数据无法证明交易支撑、目标或成交条件，宁可该板块空缺，不猜数据。此附表不得新增或修改任何 GitHub 业务 JSON、schema、字段、数组、顺序或 handoff；不得改变原主流程、Trend Handoff、Top5/6、Transmission、Expectation、Risk–Reward、READY/WAIT 原状态/原因、价格区间、发布 Gate、全量主榜、分板块摘要、审计与调度。对用户只增加一张条件触发的 Markdown 表格；不将附表判断写回持久化内容。

**分板块可见性（零 READY/WAIT 也必须输出）**：主榜单之后，按本轮 trend_handoff.signals 原顺序展示**每个输入趋势/板块**的研究去向，哪怕该板块最终 READY=0、WAIT=0。每个板块至少写明路由覆盖公司数、硬过滤后数量、进入深度研究数量、READY/WAIT 数量、EARLY_EVIDENCE 及 UNCERTAIN/DROP 的数量和主要原因；对有直接关联但未入主榜的公司，用精简附表列代表性公司、当前 Transmission/最终阶段、关键核实证据或缺口、下一次可改变分类的条件。明确“未入可执行买点榜 ≠ 未被研究 ≠ 趋势失效”。报告不得把 EARLY_EVIDENCE/UNCERTAIN 偷换成 WAIT，不给未通过估值 Gate 的公司编造价格区间，不扩大正式 handoff 的 READY/WAIT 集合；数量应能从本轮 frozen universe、pre-screen、transmission、formal arrays 去重重算，按行业与主题归属避免双计。

**发送正文与持久化分开核验**：19:00 正式版成功发布后，必须在当轮面向用户的最终正文实际呈现完整 READY/WAIT 主榜（为零时明确写零）、上述全部板块摘要及持久化状态，不能仅说“已保存 GitHub”、只给链接或只输出 machine status。GitHub COMPLETE 代表文件结果已发布，不单独证明聊天报告正文已显示；若无法确认用户可见传递，不得声称通知或正文已成功送达。此要求不改动 JSON schema、研究筛选、价格规则、持久化 Gate 或通知开关。

主榜单不得省略价格区间。正式结果即使内部 COMPLETE，但若用户可见输出没有主榜单，也视为输出不完整。

## 7. 研究纪律

- 不为了填数字而伪造估值区间；
- 无法形成可辩护估值时宁可转 UNCERTAIN；
- 榜单价格区间是研究结果，不是保证成交或收益；
- 当前价必须来自本轮正式收盘 frozen working set；
- 价格区间若因新财报、订单、重大事件或价格大幅波动失效，应在下一次正式版重新计算。
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

### 6.1 仅在全 WAIT 时展示「最值得关注的个股」

**定位与触发条件（仅为用户可见的附表）：** 在本轮已有合法榜单结果的前提下，仅当 `ready.length === 0 && wait.length > 0` 时，才在完整 READY/WAIT 主榜之后、原有分板块研究去向之前，额外展示一张标题严格为 **「最值得关注的个股」** 的表格。19:00 正式版、手动正式版使用本轮已通过发布 Gate 的正式结果；07:00 早间增量版仅在其所依赖的正式基线合法且可展示时，依据本轮已经完成的增量复核结果判断是否触发。存在任何 READY、没有 WAIT、正式结果未通过 Gate 或早间基线不可用时，不生成该表；不得将失败或旧数据伪装成新榜。

**按趋势板块而非三级行业选代表：** 以本轮 `trend_handoff.signals` 的趋势/板块为分组单位，沿用本轮已经验证过的三级行业路由和公司归属，按 signals 原顺序展示。动力煤与焦煤同属「煤炭」板块，只共享**一个**首选名额；其他趋势同理。仅从该板块已经属于正式 `wait` 的公司中选取，**每个板块最多一只，不强制凑数**。公司若明确归属多个趋势，只按本轮 signals 中优先级最高且关联可核实的趋势展示一次，避免跨板块重复；归属不能确认时不猜测。

**相对关注优先级（不重新执行筛选）：** 只比较正式结果已存在的公司级事实和判断，不重新研究、不重新估值、不抓取新行情、不重新计算或改写原排名。必须先确认公司原状态为 WAIT、Transmission=SUPPORTED、已具备可信的价格区间和明确等待/触发条件；优先考虑 Expectation=EARLY/CONFIRMING 且核心商业传导、估值假设未被已知反证破坏的公司；Expectation=PRICED_IN/EXHAUSTED 且未有已核实独立预期重置的公司，不作为板块优先关注代表。合格候选优先按原有 `risk_reward_ratio` 高到低比较；差异不足以区分时，依次参考现价与原低风险买入区上沿的相对距离、原榜 `rank`，并在表内解释取舍。不能可靠判断候选优先级时该板块留空或注明「暂无合适首选」，不为了凑表格而推荐。

**附表字段及风险说明：** 表格至少包含「板块｜最值得关注的个股｜当前价｜低风险买入区｜状态｜优先关注理由及继续等待的条件」；公司必须明确保持 WAIT，注明「相对最值得关注 ≠ 当前可以买入；仍须满足原有 READY 规则」。价格、风险收益和预期均来自本轮已完成的正式结果；这张表不能被解读为独立买卖信号或第二个执行榜单。

**严格不改变任何其他流程或持久化结果：** 此附表仅在用户可见的最终文字/Markdown 中生成，不增删改 `research/latest_formal_result.json`、`research/low_risk_handoff.json`、`research/trend_handoff.json` 或任何 JSON schema/字段/排序/数量；不改变 Universe、路由、硬过滤、Top5/6、Transmission、Expectation、Risk–Reward、READY/WAIT 状态与原因、价格区间、审核/发布 Gate、原 READY/WAIT 全量主榜、分板块摘要及既有任务调度。没有 READY 时仍必须完整输出原 WAIT 主榜；本附表只是额外信息，不替代任何原有内容。

**分板块可见性（零 READY/WAIT 也必须输出）**：主榜单之后，按本轮 trend_handoff.signals 原顺序展示**每个输入趋势/板块**的研究去向，哪怕该板块最终 READY=0、WAIT=0。每个板块至少写明路由覆盖公司数、硬过滤后数量、进入深度研究数量、READY/WAIT 数量、EARLY_EVIDENCE 及 UNCERTAIN/DROP 的数量和主要原因；对有直接关联但未入主榜的公司，用精简附表列代表性公司、当前 Transmission/最终阶段、关键核实证据或缺口、下一次可改变分类的条件。明确“未入可执行买点榜 ≠ 未被研究 ≠ 趋势失效”。报告不得把 EARLY_EVIDENCE/UNCERTAIN 偷换成 WAIT，不给未通过估值 Gate 的公司编造价格区间，不扩大正式 handoff 的 READY/WAIT 集合；数量应能从本轮 frozen universe、pre-screen、transmission、formal arrays 去重重算，按行业与主题归属避免双计。

**发送正文与持久化分开核验**：19:00 正式版成功发布后，必须在当轮面向用户的最终正文实际呈现完整 READY/WAIT 主榜（为零时明确写零）、上述全部板块摘要及持久化状态，不能仅说“已保存 GitHub”、只给链接或只输出 machine status。GitHub COMPLETE 代表文件结果已发布，不单独证明聊天报告正文已显示；若无法确认用户可见传递，不得声称通知或正文已成功送达。此要求不改动 JSON schema、研究筛选、价格规则、持久化 Gate 或通知开关。

主榜单不得省略价格区间。正式结果即使内部 COMPLETE，但若用户可见输出没有主榜单，也视为输出不完整。

## 7. 研究纪律

- 不为了填数字而伪造估值区间；
- 无法形成可辩护估值时宁可转 UNCERTAIN；
- 榜单价格区间是研究结果，不是保证成交或收益；
- 当前价必须来自本轮正式收盘 frozen working set；
- 价格区间若因新财报、订单、重大事件或价格大幅波动失效，应在下一次正式版重新计算。
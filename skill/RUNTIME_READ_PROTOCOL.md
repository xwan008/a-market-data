# A股低风险买点榜：运行时读取协议

> 本文件只约束运行时数据读取、完整性校验和研究阶段边界。选股、行业判断、公司研究、估值、买点与排名规则，以同一锁定提交下的 `skill/SKILL.md` 为准。

## 1. 核心原则

本任务采用：

> **核心数据可信就继续研究；不确定性出现在哪里，就只影响哪里。**

必须区分三类东西：

1. **全局硬阻断**：只有会系统性污染整份榜单的问题才允许终止任务；
2. **候选级不确定性**：单公司、单行业、单字段或单次研究失败，只影响对应候选；
3. **审计指标**：用于说明研究覆盖和结果质量，不作为额外熔断器。

不得为了追求“所有环节完美”而把局部缺口升级成全局失败。

---

## 2. 新 run 与版本锁定

每次定时触发、手动触发或用户明确要求重新执行，都视为新 run：

1. 获取 `xwan008/a-market-data` 当前 `main` commit SHA，记为 `locked_sha`；
2. 本轮规则与 runtime 数据均来自同一 `locked_sha`；
3. 固定读取：
   - `skill/RUNTIME_READ_PROTOCOL.md`
   - `skill/SKILL.md`
   - `data/runtime/meta.json`
4. 禁止在同一 run 中混用新旧 SHA；
5. 禁止把上一轮候选、公司分组或 detail 研究结论直接当成本轮事实。

---

## 3. 正式 runtime 入口

只使用：

- `data/runtime/meta.json`
- `meta.industry_state_file`
- `meta.screening_file`
- `meta.detail_file_template` 指向的 deep-read 公司 detail
- `skill/SKILL.md`

不得读取旧候选池或历史榜单来补齐当前 runtime。

`screening_file` 是全量轻量研究输入，不要求预先包含真实主营、核心盈利驱动或主要业务结构。`business_tags`、`core_profit_driver`、`major_business_segments` 等公司研究信息属于 deep research 阶段。

screening 阶段所需的关键轻量字段已经由 runtime 提供，包括估值、ROE、收入/利润变化、现金流以及支撑、成交密集区、20/60 日位置等价格结构数据。只要 meta 声明的 schema 与 runtime validation 通过，不得为了本次筛选另外改造数据源或临时扩展候选字段。

---

## 4. 唯一全局硬门：Runtime Hard Gate

只有以下情况允许终止整个任务：

- 当前应使用的正式 runtime 缺失或明显过期；
- `runtime_validation.status != "passed"`；
- `snapshot.trade_date` 与当前应使用的最近有效 A 股正式收盘不一致；
- meta 中核心 count / integrity 明显互相冲突，导致无法信任整个候选集；
- 必需的 `meta`、`industry_state_file` 或 `screening_file` 在锁定 SHA 下无法取得；
- compact 行业或候选数据无法通过任何可靠方式完整消费；
- 同一 run 中无法维持单一 `locked_sha`，出现版本混用风险。

除此之外，原则上**不得终止整份榜单**。

当 Runtime Hard Gate 通过后，应直接信任 GitHub 生成侧已完成的机械完整性校验，不再重新逐窗口证明 EOF、行数、唯一性、列数或 schema。

---

## 5. 不属于全局失败的情况

以下情况不得阻断整个任务：

- 单个字段为空；
- 单个候选 detail 无法读取；
- 某家公司公开资料不足；
- 某家公司主营、盈利驱动或估值暂时无法可靠确认；
- 某个行业证据不足；
- 某只股票存在数据冲突；
- 某些 `deep_read_codes` 无法完成全部研究；
- screening 中不存在 `business_tags`、`core_profit_driver`、`major_business_segments`；
- 工具 UI 对大文件显示 `truncated`，但仍有其他可靠方式消费完整数据；
- 未读取非 deep-read 公司的 detail。

这些问题只允许产生候选级状态：

- `confirmed`
- `research_uncertain`
- `waiting`
- `excluded`

不得自动升级为整轮失败。

---

## 6. 全行业与全候选轻量覆盖

Runtime Hard Gate 通过后：

- 覆盖全部 runtime 行业；
- 让全部机械候选进入基于 compact 数据的轻量比较流程；
- 不得只研究热点行业或当日强势方向；
- 不得因为已经找到足够多好公司而提前停止扫描全量候选。

“全候选覆盖”仅意味着每个候选都进入轻量 screening，不意味着必须逐家公司公开检索。

前置阶段直接使用申万三级行业作为初始可比组，并按 `SKILL.md` 固定执行：

1. **潜在结构相关性检查**：只使用 runtime 已有的 `support_center`、`volume_zone_center`、`position_pct` 等结构字段；
2. **同组三维非补偿比较**：价格结构、估值质量、经营质量；
3. 不得形成跨维度加权总分，不得用行业强弱或趋势单独淘汰公司。

必须区分：screening 的结构线索不等于最终 `low_risk_buy_range`。最终安全区只能在 deep research 和估值阶段形成。

---

## 7. deep_read_codes 的形成

`deep_read_codes` 必须严格服从当前 `SKILL.md` 的准入逻辑，不得再使用旧的“综合排名后取 Top N”方式。

### 7.1 潜在结构相关性

使用 compact runtime 的现成字段判断：

- 当前价接近 `support_center`；
- 当前价接近 `volume_zone_center`；
- 当前价位于 60 日相对低位。

具体阈值和组合规则以同一 `locked_sha` 下的 `SKILL.md` 为准。

这一阶段只决定“当前价格是否值得投入进一步研究资源”，不是对公司估值或最终安全区下结论。

### 7.2 同组明确支配

只对已经具有潜在结构相关性的候选，在同一申万三级行业内比较：

- 价格结构；
- 估值质量；
- 经营质量。

候选只有在存在同组同行对其构成 `SKILL.md` 定义的明确支配时，才允许在 deep-read 前排除。

如果三个维度互有胜负、业务异质性明显、周期属性可能扭曲估值、数据冲突或无法可靠判断支配关系，应保守进入 `deep_read_codes`。

不得：

- 机械只保留每组 Top1 / Top2；
- 设全市场综合评分榜并截取 Top N；
- 因市场风险高而缩小已经满足准入规则的 deep-read 范围；
- 因行业只是 `stable`、趋势是 `transition/bearish` 而单独排除公司。

对每个因同组明确支配而未进入 `deep_read_codes` 的候选，执行过程必须能够追溯：

- `dominated_by`：替代它的同组公司；
- 价格结构比较；
- 估值质量比较；
- 经营质量比较。

这些追溯信息可以只在内部研究记录中维护，不要求全部展示给用户；但用户追问某只股票为什么被筛掉时，必须能基于当前 run 重新说明，而不能回答“综合排名较低”。

---

## 8. Deep Research 与局部降级

只读取 `deep_read_codes` 对应的 detail，并在必要时使用公开资料确认：

- 真实主营 / `business_tags`；
- 核心盈利驱动 / `core_profit_driver`；
- 主要业务与利润来源 / `major_business_segments`；
- 行业机会是否真实传导到公司；
- 是否存在一次性收益、周期高点或其他估值扭曲；
- 未来 1–2 个季度盈利逻辑和主要反向证据。

如果某个 deep-read 公司无法完成上述研究：

- 不得因此阻断整轮任务；
- 将该公司标记为 `research_uncertain` 或 `waiting`；
- 不允许它进入正式推荐，除非核心结论已得到足够证据支持。

如果同一三级行业内公司实际不可比，应重新分组；如果跨三级行业公司的核心盈利驱动高度一致，也允许形成新的真实可比组。

最终 `low_risk_buy_range`、`base_fair_value` 和 `conservative_upside` 均属于这一阶段之后的公司级研究结论，不得从 screening 的单一支撑位直接复制。

---

## 9. 发布规则

Runtime Hard Gate 通过后，原则上允许发布正式结果。

正式推荐中的每一只股票必须自身满足：

- 核心公司与行业逻辑已确认；
- 估值和最终安全边际有足够依据；
- 向下空间与保守向上空间能够合理判断；
- 关键风险与推翻条件已明确；
- 没有未解决到足以改变买入结论的重大不确定性。

未满足这些条件的公司可以进入等待池、`research_uncertain` 或淘汰，但**不得因为它们存在而阻止其他已确认公司发布。**

允许正式榜为空；空榜代表当前没有满足条件的公司，而不是任务失败。

---

## 10. 审计只记录，不熔断

最终至少记录：

- `snapshot.trade_date`
- `mechanical_candidate_count`
- `industry_coverage_count`
- `structural_relevance_count`
- `peer_dominated_count`
- `deep_read_codes_count`
- `company_confirmed_count`
- `research_uncertain_count`
- `waiting_count`
- `final_recommendation_count`

其中：

- `structural_relevance_count`：通过当前 `SKILL.md` 潜在结构相关性规则的候选数；
- `peer_dominated_count`：因同组明确支配而未进入 deep-read 的候选数。

这些字段用于解释研究覆盖和不确定性，不要求全部达到某个数值才能发布。

只有 Runtime Hard Gate 状态需要明确给出 `PASS / FAIL`。

---

## 11. 收盘版与早间增量版

### 收盘正式版

基于锁定 SHA 的 validated compact runtime：

全行业 / 全候选轻量覆盖 → 三级行业初分组 → 潜在结构相关性 → 同组三维非补偿比较 → `deep_read_codes` → 公司级 deep research → 最终估值与安全边际 → 正式榜 / 等待池 / 不确定 / 淘汰。

局部研究失败只影响对应候选。

### 早间隔夜增量版

重新锁定当前 main 并读取当前规则与 meta；允许以上一有效收盘版决策结论为比较基准，只复核隔夜新增信息是否改变：

- 行业景气；
- 公司盈利；
- 最终安全边际；
- 保守向上空间；
- 重大风险与推翻条件。

不得把早间版重新退化成完整机械校验流程。

---

## 12. 最终原则

> **screening 负责分配研究注意力，不负责提前完成最终估值。**

> **价格结构、估值质量、经营质量不能压成一个可相互补偿的综合总分。**

> **全局问题才全局停止，局部问题只局部降级。**

> **审计用于解释质量，不用于制造新的熔断器。**

> **只要 Runtime Hard Gate 通过，就尽最大可能完成并发布当前可可靠得出的研究结果。**
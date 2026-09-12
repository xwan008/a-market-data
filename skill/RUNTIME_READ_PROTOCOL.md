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

“全候选覆盖”仅意味着每个候选都进入轻量比较，不意味着必须逐家公司公开检索。

前置阶段允许直接使用申万三级行业作为初始可比组，并结合：

- 行业状态；
- 估值；
- 盈利变化；
- ROE、现金流、毛利率等基础质量；
- 价格位置；
- 支撑、成交密集区、阻力与失效结构；
- 趋势与市场环境。

---

## 7. deep_read_codes 的形成

前置轻量比较的目的只是确定哪些公司值得进一步研究。

`deep_read_codes` 应自然包含：

- 具有潜在安全边际的公司；
- 具有潜在明显上行空间的公司；
- 估值、盈利、现金流或价格结构具有差异化价值的公司；
- 明显龙头或高质量代表公司，除非已有充分排除理由；
- 因业务异质性、周期属性、数据冲突或行业映射不足而无法可靠前置判断的 `research_uncertain`。

`deep_read_codes` 不设全局数量上限或下限，也不得机械只保留每组 Top1 / Top2。

形成 `deep_read_codes` 之前，不要求全部候选拥有公司级业务字段。

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

---

## 9. 发布规则

Runtime Hard Gate 通过后，原则上允许发布正式结果。

正式推荐中的每一只股票必须自身满足：

- 核心公司与行业逻辑已确认；
- 估值和安全边际有足够依据；
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
- `deep_read_codes_count`
- `company_confirmed_count`
- `research_uncertain_count`
- `waiting_count`
- `final_recommendation_count`

这些字段用于解释研究覆盖和不确定性，不要求全部达到某个数值才能发布。

只有 Runtime Hard Gate 状态需要明确给出 `PASS / FAIL`。

---

## 11. 收盘版与早间增量版

### 收盘正式版

基于锁定 SHA 的 validated compact runtime：

全行业 / 全候选轻量覆盖 → 三级行业初分组 → 自然形成 `deep_read_codes` → 公司级 deep research → 估值与安全边际 → 正式榜 / 等待池 / 不确定 / 淘汰。

局部研究失败只影响对应候选。

### 早间隔夜增量版

重新锁定当前 main 并读取当前规则与 meta；允许以上一有效收盘版决策结论为比较基准，只复核隔夜新增信息是否改变：

- 行业景气；
- 公司盈利；
- 安全边际；
- 保守向上空间；
- 重大风险与推翻条件。

不得把早间版重新退化成完整机械校验流程。

---

## 12. 最终原则

> **全局问题才全局停止，局部问题只局部降级。**

> **审计用于解释质量，不用于制造新的熔断器。**

> **只要 Runtime Hard Gate 通过，就尽最大可能完成并发布当前可可靠得出的研究结果。**

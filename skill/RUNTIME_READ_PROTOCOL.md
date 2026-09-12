# A股低风险买点榜｜运行时执行协议

本文件只定义：

- 如何锁定版本；
- 读取哪些正式 runtime 输入；
- 什么情况允许整轮停止；
- Pre-Research 与 Deep Research 的执行顺序；
- Ledger 冻结和 coverage 审计；
- Deep Research 完成后的风险簇归并与最终机会榜审计。

具体公司判断、Deep Research、估值、Risk Cluster Consolidation 与买点语义，以同一 SHA 下的 `skill/SKILL.md` 为准。

---

## 1. 每轮锁定一个 SHA

每个新 run：

1. 获取 `xwan008/a-market-data` 当前 `main` commit SHA，记为 `locked_sha`；
2. 同一 run 中所有仓库读取都使用该 `locked_sha`；
3. 禁止混用不同 SHA；
4. 禁止把上一轮同行判断、预筛结果或公司研究结论直接当成本轮事实。

---

## 2. 正式输入

从同一 `locked_sha` 读取：

- `skill/RUNTIME_READ_PROTOCOL.md`
- `skill/SKILL.md`
- `data/runtime/meta.json`
- `meta.screening_group_file`
- `meta.candidate_file`：只在 Deep Research 对冻结幸存者需要更完整确定性字段时按需读取。

正式模型入口不再包括：

- `peer_groups.json`
- `company_research_view.json`
- `data/runtime/details/`
- `data/runtime/screening_snapshot.json`
- `data/runtime/industry_state_compact.json`

`screening_group_file` 是全部不联网预筛的唯一结构化工作视图。

---

## 3. Runtime Hard Gate

只有以下情况允许终止整轮任务：

- 正式 runtime 缺失或明显过期；
- `runtime_validation.status != "passed"`；
- snapshot 交易日不是当前应使用的最近有效 A 股正式收盘；
- `meta.json`、`screening_group_file` 或 `candidate_file` 无法读取 / 解析；
- `screening_group_validation.status != "passed"`；
- screening group 股票全集与 candidate 股票全集冲突；
- runtime 的 YoY 单位不是 `percentage_points`；
- 同一 run 无法维持一个 `locked_sha`。

单个公司资料不足、估值不确定、业务难以判断，都不是全局 Hard Gate。

---

## 4. 程序筛选信任边界

`runtime_validation.status == "passed"` 表示生成侧已经确定性验证：

- Eligibility Filter 生成了候选全集；
- Eligibility audit 能从全市场总数闭合到 `source_candidate_count`；
- Structure Filter 使用正式结构规则；
- `candidate_count == structural_relevance_count`；
- candidate code 唯一；
- screening group code 唯一；
- screening group 与 candidate 股票全集完全一致；
- `structure_tier / strong_support / strong_volume_zone` 已由程序正式计算；
- YoY 单位已统一为 percentage points。

模型不得重新逐只计算或修改这些程序资格结论。

具体结构阈值只读取 `meta.structural_rule`；协议和 Skill 不再复制一套参数。

---

## 5. Pre-Research Screening｜禁止联网

第一阶段只读取 `screening_group_file`。

按组处理全部 model-ready candidates，并严格使用 `SKILL.md` 中的顺序：

1. 先判断 `PEER_DOMINATED`；
2. 对未被同行支配者再判断：
   - `CLEARLY_WEAK`
   - `PASS_TO_DEEP_RESEARCH`
   - `UNCERTAIN`

单只组跳过同行支配判断，但不能跳过公司绝对质量判断。

这一阶段禁止任何公司级 Web 查询、新闻搜索或公开资料 Deep Research。

---

## 6. 必须先冻结完整 Pre-Research Ledger

在任何公司级 Web 查询之前，必须先完成全部候选的 Pre-Research Ledger。

每只结构候选最终恰好出现一次，例如：

```text
code | result | reason_code
000750 | PEER_DOMINATED | dominated_by=XXXXXX
600273 | CLEARLY_WEAK | multi_dimension_deterioration
000338 | PASS_TO_DEEP_RESEARCH | fundamentals_ok
605020 | UNCERTAIN | cyclical_context
```

Ledger 冻结后形成互斥集合：

- `peer_dominated_codes`
- `clearly_weak_codes`
- `pass_to_deep_research_codes`
- `uncertain_codes`

并定义：

```text
deep_read_codes
=
pass_to_deep_research_codes
∪ uncertain_codes
```

必须满足：

```text
candidate_codes
=
peer_dominated_codes
∪ clearly_weak_codes
∪ pass_to_deep_research_codes
∪ uncertain_codes
```

且四个集合互斥。

**在 `deep_read_codes` 冻结之前，不得开始任何公司级 Web 查询。**

这只是一个明确阶段边界，不建立复杂状态机、窗口管理或逐股票 checkpoint。

---

## 7. Deep Research

第三阶段唯一允许主动研究的公司集合是冻结后的 `deep_read_codes`。

不得：

- 重新自由挑选；
- 因为已经找到几只好公司就提前停止；
- 用实际搜索过的公司反推本应研究的公司；
- 因市场风险高而缩小冻结集合。

需要完整确定性背景时，按 `deep_read_codes` 从 `candidate_file` 中读取对应公司即可，不要求重新扫描全部候选。

对每个 `deep_read_code` 最终形成足以进入：

- `confirmed`
- `waiting`
- `research_uncertain`
- `excluded`

之一的公司级研究状态。

Deep Research 同时应留下最终风险簇归并所需要的公司级事实，包括 `primary_profit_driver` 与 `dominant_risk_factor`；具体判断语义由 `SKILL.md` 定义。

---

## 8. Deep Research coverage

第三阶段同时维护：

- `expected_deep_research_codes = deep_read_codes`
- `actual_deep_researched_codes`

只有完成足以形成公司级研究状态的公开资料核验，才计入 `actual_deep_researched_codes`；搜索请求次数不等于研究完成数。

结束时：

### COMPLETE

```text
expected_deep_research_codes
==
actual_deep_researched_codes
```

### INCOMPLETE

集合不相等，必须列出：

- `missing_deep_research_codes`
- `unexpected_researched_codes`（如有）

### UNVERIFIED

没有先冻结完整 Ledger，或者无法恢复 `deep_read_codes`。

不得把“实际搜索覆盖 N 只”冒充“按规则本应 Deep Research 的就是 N 只”。

正式闭环应以 `coverage = COMPLETE` 为目标；若不是 COMPLETE，必须明确说明本轮研究覆盖未闭合。

---

## 9. Final Opportunity Consolidation｜最终机会归并

只有在公司级 Deep Research、估值和 `deep_research_coverage` 状态已经确定之后，才进行最终风险簇归并。

具体如何判断同一 `risk_cluster`、如何选择代表公司、何时允许同一行业多个独立机会，由 `SKILL.md` 定义。

执行层只要求：

1. 风险簇归并不得改变 `deep_read_codes`；
2. 风险簇归并不得修改 `actual_deep_researched_codes`；
3. 公司级 `confirmed / waiting / research_uncertain / excluded` 状态保持不变；
4. 正式榜排名对象改为**独立风险收益机会**，同一风险簇默认一个 `representative_code`；
5. 同簇其他仍有价值的公司保留为 `alternative_codes`；
6. 若同一行业有多个正式席位，必须记录 `independence_rationale`；
7. 若 `deep_research_coverage != COMPLETE`，最终机会榜必须明确标记研究覆盖未闭合，不得声称是完整机会全集。

风险簇归并是发布层去相关，不是研究层淘汰。

---

## 10. 最终审计漏斗

正式结果至少记录：

- `snapshot.trade_date`
- `universe_count`
- `source_candidate_count`
- Eligibility Filter 各互斥排除原因数量
- `structural_relevance_count`
- `screening_group_count`
- `peer_dominated_count`
- `company_prescreen_count`
- `company_clearly_weak_count`
- `pass_to_deep_research_count`
- `uncertain_prescreen_count`
- `deep_research_candidate_count`
- `actual_deep_researched_count`
- `deep_research_coverage`
- `company_confirmed_count`
- `research_uncertain_count`
- `waiting_count`
- `risk_cluster_count`
- `formal_opportunity_count`
- `final_recommendation_count`（与 `formal_opportunity_count` 同口径，表示独立机会数，不再表示股票数）

并保留至少以下代码集合或映射：

- `peer_dominated_codes`
- `clearly_weak_codes`
- `pass_to_deep_research_codes`
- `uncertain_codes`
- `deep_read_codes`
- `actual_researched_codes`
- `formal_representative_codes`
- `risk_cluster_map`：每个 cluster 至少包含 `representative_code` 与 `alternative_codes`
- `independence_rationale`：同一行业存在多个正式独立机会时记录。

必须区分：

```text
company_confirmed_count
```

与：

```text
formal_opportunity_count
```

前者是公司级研究结果数量，后者是去除共同主导风险因子后的正式独立机会数量。

---

## 11. 市场风险与执行覆盖

市场 `bearish / weak breadth / high risk` 只能影响最终估值、等待倾向和正式榜数量。

它不得：

- 改变程序候选全集；
- 跳过 Pre-Research Screening；
- 改变冻结后的 `deep_read_codes`；
- 成为研究覆盖不完整的理由；
- 被用来绕过 Risk Cluster Consolidation，重复发布同一风险暴露。

---

## 12. 执行原则

> **先完整筛选，再冻结名单，再联网研究。**

> **先完成公司级研究，再做最终风险因子去重。**

> **程序资格不由模型重算。**

> **本轮应研究集合与实际研究集合必须分开记录。**

> **研究覆盖完整性和最终榜风险去重是两件不同的事。**

> **不要用复杂流程控制替代清楚的阶段边界。**

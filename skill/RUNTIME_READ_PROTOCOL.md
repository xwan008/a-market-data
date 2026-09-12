# A股低风险买点榜｜运行时执行协议

本文件只定义：

- 如何锁定版本；
- 读取哪些正式 runtime 输入；
- 什么情况允许整轮停止；
- Pre-Research 与 Deep Research 的执行顺序；
- Ledger 冻结和 coverage 审计。

具体公司判断、Deep Research、估值与买点语义，以同一 SHA 下的 `skill/SKILL.md` 为准。

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

## 9. 最终审计漏斗

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
- `final_recommendation_count`

并保留至少以下代码集合：

- `peer_dominated_codes`
- `clearly_weak_codes`
- `pass_to_deep_research_codes`
- `uncertain_codes`
- `deep_read_codes`
- `actual_researched_codes`

---

## 10. 市场风险与执行覆盖

市场 `bearish / weak breadth / high risk` 只能影响最终估值、等待倾向和正式榜数量。

它不得：

- 改变程序候选全集；
- 跳过 Pre-Research Screening；
- 改变冻结后的 `deep_read_codes`；
- 成为研究覆盖不完整的理由。

---

## 11. 执行原则

> **先完整筛选，再冻结名单，再联网研究。**

> **程序资格不由模型重算。**

> **本轮应研究集合与实际研究集合必须分开记录。**

> **不要用复杂流程控制替代清楚的阶段边界。**

# A股低风险买点榜｜运行时执行协议

本文件只定义执行契约：

- 如何锁定正式 runtime 与规则版本；
- 单次任务中 Stage A → Frozen Ledger Hard Gate → Stage B 的严格串行顺序；
- Frozen Ledger 的固定字段契约、逐公司审计和并发写安全；
- 什么情况必须停止；
- Deep Research coverage 如何闭合；
- coverage COMPLETE 后如何进入 Risk Cluster 与正式机会榜。

具体公司判断、Deep Research、估值、Risk Cluster Consolidation 与买点语义，以同一轮锁定的 `skill/SKILL.md` 为准。

---

## 1. 总体架构｜一次触发，两个严格串行阶段

每次“A股低风险买点榜”触发只运行一次完整任务：

```text
单次任务触发
↓
Stage A｜Structured Screening Freeze
只使用锁定 GitHub runtime 中的结构化事实
↓
完整逐公司 Ledger
↓
持久化 research/pre_research_ledger.json
status = FROZEN
↓
重新读取 Frozen Ledger + 正式文件
↓
Frozen Ledger Hard Gate
↓
PASSED
↓
Stage B｜Deep Research + Publication
只消费 frozen deep_read_codes
↓
Deep Research coverage audit
↓
COMPLETE
↓
Risk Cluster Consolidation
↓
正式独立机会榜
```

Stage A 与 Stage B 属于**同一次任务执行中的两个串行阶段**。真正的边界是持久化并回读验证的 Frozen Ledger，不是时间间隔，也不是“模型觉得自己已经做完 Stage A”。

- Stage A 不承担公司级公开资料 Deep Research，不生成正式榜；
- Stage B 不重新做同行支配或公司绝对质量预筛，不修改 frozen `deep_read_codes`；
- 每次新任务都先执行 Stage A，不直接把上一轮 Ledger 当成本轮事实。

---

## 2. 正式文件与非正式文件

### 2.1 正式输入

本任务正式输入只有：

- `skill/RUNTIME_READ_PROTOCOL.md`
- `skill/SKILL.md`
- `data/runtime/meta.json`
- `meta.screening_group_file`
- `meta.candidate_file`

### 2.2 阶段检查点

唯一正式阶段检查点：

- `research/pre_research_ledger.json`

它不是市场数据源，而是本轮 Stage A 的可审计产物。

### 2.3 不属于正式输入

正式模型入口不包括：

- `peer_groups.json`
- `company_research_view.json`
- `data/runtime/details/`
- `data/runtime/screening_snapshot.json`
- `data/runtime/industry_state_compact.json`
- 任何历史 `deep_research_results_*`、旧榜单、旧公司研究结论或其他 research 结果文件。

历史结果只能用于人工复盘，**不得作为本轮 Structured Screening、Deep Research 或估值事实输入**。

`screening_group_file` 是 Stage A 的唯一模型工作视图；`candidate_file` 主要供 Stage B 对 frozen 代码补充完整确定性背景。

---

## 3. Runtime Hard Gate

出现以下任一情况，停止整轮任务：

- 正式 runtime 缺失或明显过期；
- `runtime_validation.status != "passed"`；
- snapshot 交易日不是当前应使用的最近有效 A 股正式收盘；
- `meta.json`、`screening_group_file` 或 `candidate_file` 无法读取 / 解析；
- `screening_group_validation.status != "passed"`；
- screening group 股票全集与 candidate 股票全集冲突；
- runtime 的 YoY 单位不是 `percentage_points`。

单个公司资料不足、估值不确定、业务难以判断，都不是全局 Runtime Hard Gate。

---

## 4. 程序筛选信任边界

`runtime_validation.status == "passed"` 表示生成侧已经确定性验证：

- Eligibility Filter 生成候选全集；
- Eligibility audit 从全市场总数闭合到 `source_candidate_count`；
- Structure Filter 使用正式结构规则；
- `candidate_count == structural_relevance_count`；
- candidate code 唯一；
- screening group code 唯一；
- screening group 与 candidate 股票全集完全一致；
- `structure_tier / strong_support / strong_volume_zone` 已由程序正式计算；
- YoY 单位统一为 `percentage_points`。

模型不得重新逐只计算或修改这些程序资格结论。

具体结构阈值只读取 `meta.structural_rule`；Protocol 和 Skill 不复制另一套易漂移参数。

---

## 5. Stage A｜Structured Screening Freeze

### 5.1 锁定本轮正式输入

Stage A 开始时：

1. 获取当前 `main` commit SHA，记为 `source_runtime_commit_sha`；
2. 从该版本读取 Protocol、Skill、`meta.json`、`screening_group_file`、`candidate_file`；
3. 记录五个正式文件 Git blob SHA：
   - `protocol_blob_sha`
   - `skill_blob_sha`
   - `meta_blob_sha`
   - `screening_group_blob_sha`
   - `candidate_blob_sha`
4. 生成本轮唯一 `run_id`。`run_id` 只用于区分并发/重叠执行，不参与投资判断；
5. Stage A 后续结构化判断只使用上述锁定输入。

写 Ledger 自己会改变 `main` commit SHA，因此后续同一输入一致性使用五个正式文件的 **blob SHA** 判断，不要求 current main SHA 等于 `source_runtime_commit_sha`。

### 5.2 先使旧 Ledger 失效

在开始本轮 Model Prescreen 前，必须把：

```text
research/pre_research_ledger.json
```

写为本轮：

```text
status = BUILDING
run_id = <本轮唯一值>
```

同时写入五个正式 blob SHA、trade_date、candidate_count、信息边界字段，并清空本轮判断集合与 `ledger_entries`。

写入后必须重新读取该文件，确认：

- `status == BUILDING`
- `run_id` 与本轮一致
- 五个正式 blob SHA 与本轮锁定值一致。

若回读不一致，说明存在写入冲突或并发覆盖，停止整轮任务。

只要本轮 Stage A 已启动，上一轮 FROZEN Ledger 就立即失效。

### 5.3 Repository-only 信息边界

Stage A 可以访问 GitHub，因为必须读取仓库正式 runtime。

但在本轮 Ledger 成功 FROZEN **并重新读取通过 Hard Gate 之前**，禁止引入：

- 公司官网；
- 公司公告正文或交易所外部页面；
- 新闻；
- 券商研报；
- 搜索引擎结果；
- 行业网站或其他公司级外部公开资料。

准确语义是：

> **Repository-only Structured Screening，而不是“完全不能联网”。**

若 FROZEN 前发生任何公司级外部资料查询：

```text
stage_a_information_boundary = VIOLATED
external_company_research_before_freeze = true
```

Ledger 必须保持 `FAILED` / 非 FROZEN，`Deep Research coverage = UNVERIFIED`，停止整轮任务。

不得通过“先查外部资料、之后再补齐 Structured Screening”恢复可验证性。

### 5.4 完成全部 Model Prescreen

按 `SKILL.md` 对 `screening_group_file` 中全部候选完成：

1. 先判断 `PEER_DOMINATED`；
2. 未被同行支配者再判断：
   - `CLEARLY_WEAK`
   - `PASS_TO_DEEP_RESEARCH`
   - `UNCERTAIN`

单只组跳过同行支配判断，但不能跳过公司绝对质量判断。

每只结构候选必须恰好出现一次。不得因为已获得足够多 Deep Research 候选、已经存在足够多潜在机会、或者想降低后续研究量而停止或改变判断标准。

`PEER_DOMINATED` 只能按 Skill 的严格公司级支配语义使用，**不得承担行业去重或 Risk Cluster 的职责**。

---

## 6. Frozen Ledger｜固定字段契约与逐公司审计

### 6.1 当前唯一字段契约

本 Protocol 直接定义当前唯一有效 Ledger 字段契约。运行时不得识别、迁移或兼容历史 Ledger 格式；任何不符合当前必需字段、逐公司审计和集合闭合要求的 Ledger 都视为无效。

### 6.2 必要顶层字段

FROZEN Ledger 至少包含：

```json
{
  "status": "FROZEN",
  "run_id": "...",
  "created_at": "ISO-8601 timestamp",
  "source_runtime_commit_sha": "...",
  "protocol_blob_sha": "...",
  "skill_blob_sha": "...",
  "meta_blob_sha": "...",
  "screening_group_blob_sha": "...",
  "candidate_blob_sha": "...",
  "trade_date": "YYYY-MM-DD",
  "candidate_count": 109,
  "ledger_count": 109,
  "repository_only": true,
  "external_company_research_before_freeze": false,
  "stage_a_information_boundary": "CLEAN",
  "peer_dominated_codes": [],
  "clearly_weak_codes": [],
  "pass_to_deep_research_codes": [],
  "uncertain_codes": [],
  "deep_read_codes": [],
  "ledger_entries": []
}
```

数字 `109` 只是示例；实际必须使用本轮 `candidate_count`。

### 6.3 四集合约束

必须形成四个互斥集合：

- `peer_dominated_codes`
- `clearly_weak_codes`
- `pass_to_deep_research_codes`
- `uncertain_codes`

并满足：

```text
deep_read_codes
=
pass_to_deep_research_codes
∪ uncertain_codes
```

```text
candidate_codes
=
peer_dominated_codes
∪ clearly_weak_codes
∪ pass_to_deep_research_codes
∪ uncertain_codes
```

且：

```text
ledger_count == candidate_count
```

### 6.4 `ledger_entries` 是正式 Ledger，不是可选说明

`ledger_entries` 必须覆盖全部候选，每个候选恰好一个 entry，至少包含：

```json
{
  "code": "000000",
  "result": "PASS_TO_DEEP_RESEARCH",
  "reason_code": "fundamentals_ok",
  "reason": "compact auditable explanation"
}
```

`result` 只能为：

- `PEER_DOMINATED`
- `CLEARLY_WEAK`
- `PASS_TO_DEEP_RESEARCH`
- `UNCERTAIN`

四个代码集合必须由 `ledger_entries[].result` 可完全重建并与其严格一致。

#### PEER_DOMINATED 额外字段

每个 `PEER_DOMINATED` entry 必须额外包含：

```json
{
  "dominated_by": "XXXXXX",
  "price_structure_basis": "...",
  "valuation_basis": "...",
  "operating_basis": "...",
  "differentiated_advantage_check": "...",
  "uncertainty_check": "..."
}
```

缺任一字段，或 `dominated_by` 不在同一 screening group，Ledger 审计失败。

`CLEARLY_WEAK` 的 `reason` 必须体现多个独立弱项；单指标理由不满足 Skill 契约。

### 6.5 FROZEN 写安全

全部判断完成后，在把 BUILDING 更新为 FROZEN 之前必须再次读取当前 Ledger，并确认：

- 当前 `status == BUILDING`
- 当前 `run_id` 与本轮一致
- 当前五个正式 blob SHA 与本轮一致。

只有确认当前文件仍属于本轮执行，才使用**当前 Ledger blob SHA**更新为 FROZEN。

若发现 `run_id` 已变化、状态不是 BUILDING、或 blob 不一致，说明另一个执行已经覆盖检查点；本轮停止，不得覆盖对方结果。

只有以下条件全部通过才允许 `status = FROZEN`：

- Stage A 信息边界 CLEAN；
- 四集合完整闭合且互斥；
- `deep_read_codes` 派生正确；
- `ledger_entries` 数量等于 `candidate_count`；
- 每个 candidate code 在 entries 中恰好一次；
- entries 结果可严格重建四集合；
- 所有 `PEER_DOMINATED` entry 支配依据完整；
- 本轮 `run_id` 写安全检查通过。

否则保持 `BUILDING` 或写成 `FAILED`。

---

## 7. Stage A → Stage B｜Frozen Ledger Hard Gate

Stage A 写入 FROZEN 后，**不得凭内存直接进入 Deep Research**。

必须重新读取：

- `research/pre_research_ledger.json`
- 当前 Protocol
- 当前 Skill
- 当前 `meta.json`
- 当前 `screening_group_file`
- 当前 `candidate_file`

Hard Gate 必须同时验证：

1. `status == FROZEN`；
2. `run_id` 与本轮 Stage A 一致；
3. `repository_only == true`；
4. `external_company_research_before_freeze == false`；
5. `stage_a_information_boundary == CLEAN`；
6. `ledger_count == candidate_count`；
7. 四类代码集合互斥且并集等于当前 candidate 全集；
8. `deep_read_codes == pass_to_deep_research_codes ∪ uncertain_codes`；
9. `ledger_entries` 完整、一致、可重建四集合；
10. 所有 PEER_DOMINATED entry 具备完整支配审计字段；
11. 当前 `trade_date` 与 Ledger 一致；
12. 当前 `candidate_count` 与 Ledger 一致；
13. 当前 Protocol / Skill / meta / screening_groups / candidates 五个 blob SHA 与 Ledger 记录完全一致。

任一条件失败：

```text
ledger_validation = FAILED
```

整轮停止，不得开始公司级公开资料研究，不得生成正式榜。

Stage B 不得重新做 Pre-Research 来修补失败 Ledger；下一次任务触发重新从 Stage A 开始。

验证通过后：

```text
expected_deep_research_codes = ledger.deep_read_codes
```

从此不得增删该集合。

---

## 8. Stage B｜Deep Research

Deep Research 唯一允许主动研究的公司集合是：

```text
ledger.deep_read_codes
```

不得：

- 重新自由挑选；
- 重新做 Peer Dominance / CLEARLY_WEAK；
- 因为已经找到几只好公司就提前停止；
- 因为已经存在“足够出榜”的 confirmed 数量就提前停止；
- 因为预计正式榜已经足够丰富就跳过剩余公司；
- 因市场风险高而缩小冻结集合；
- 使用上一轮公司研究结论替代本轮公开资料核验。

需要完整确定性背景时，从 `candidate_file` 中按 frozen codes 读取对应公司即可。

每个 `deep_read_code` 最终形成足以进入以下之一的公司级研究状态：

- `confirmed`
- `waiting`
- `research_uncertain`
- `excluded`

Deep Research 同时应形成 Risk Cluster 所需的：

- `primary_profit_driver`
- `dominant_risk_factor`

具体语义由 `SKILL.md` 定义。

本阶段完成条件不是“找到若干可推荐公司”，而是 frozen 集合全部处理。

---

## 9. Deep Research coverage｜正式榜硬门

Stage B 维护：

- `expected_deep_research_codes = ledger.deep_read_codes`
- `actual_deep_researched_codes`

只有完成足以形成公司级研究状态的公开资料核验，才计入 actual；搜索请求次数不等于研究完成数。

### COMPLETE

```text
expected_deep_research_codes
==
actual_deep_researched_codes
```

只有 `COMPLETE` 才允许进入 Risk Cluster Consolidation 和正式独立机会榜。

### INCOMPLETE

集合不相等，必须列出：

- `missing_deep_research_codes`
- `unexpected_researched_codes`（如有）

此时不得生成正式独立机会榜，也不得把已完成研究子集包装为临时正式榜、当前 Top N 或其他等价推荐结果。

### UNVERIFIED

包括但不限于：

- Stage A 在 FROZEN 前使用了公司级外部资料；
- Frozen Ledger 缺失或不是当前 schema；
- Ledger 集合/entries 无法闭合；
- Ledger 与当前正式 runtime / Skill / Protocol blob 不一致；
- 无法恢复 frozen `deep_read_codes`。

此时同样不得生成正式独立机会榜。

正式闭环唯一完成条件：

```text
deep_research_coverage = COMPLETE
```

“已经找到足够多好公司”“已经够出榜”“达到某个推荐数量”都不是完成条件。

---

## 10. Final Opportunity Consolidation｜最终机会归并

前置条件：

```text
deep_research_coverage == COMPLETE
```

只有公司级 Deep Research 全部闭合、估值完成后，才按 `SKILL.md` 进行 Risk Cluster Consolidation。

执行层要求：

1. Risk Cluster 不得改变 `deep_read_codes`；
2. 不得修改 `actual_deep_researched_codes`；
3. 公司级 `confirmed / waiting / research_uncertain / excluded` 状态保持不变；
4. 正式榜排名对象是**独立风险收益机会**；
5. 同一风险簇默认一个 `representative_code`；
6. 同簇其他仍有价值公司保留为 `alternative_codes`；
7. 同一行业存在多个正式席位时记录 `independence_rationale`；
8. 正式机会集合不设目标数量、不设固定上限、不做 Top N 截断；
9. 排名只表达优先级，不得作为停止研究或截断正式机会集合的理由。

Risk Cluster 是发布层去相关，不是研究层淘汰。

---

## 11. 最终审计漏斗

单次任务最终至少记录：

### Stage A

- `trade_date`
- `run_id`
- `candidate_count`
- `ledger_count`
- `peer_dominated_count`
- `company_clearly_weak_count`
- `pass_to_deep_research_count`
- `uncertain_prescreen_count`
- `deep_research_candidate_count`
- 四类代码集合
- `deep_read_codes`
- `ledger_entries_count`
- 五个正式文件 blob SHA
- `stage_a_information_boundary`
- `ledger_status`
- `ledger_validation`

### Stage B / 最终研究

- `snapshot.trade_date`
- `universe_count`
- `source_candidate_count`
- Eligibility Filter 各互斥排除原因数量
- `structural_relevance_count`
- `screening_group_count`
- `deep_research_candidate_count`
- `actual_deep_researched_count`
- `deep_research_coverage`
- `company_confirmed_count`
- `research_uncertain_count`
- `waiting_count`
- `excluded_count`
- `deep_read_codes`
- `actual_researched_codes`

只有 coverage COMPLETE 时才记录并发布：

- `risk_cluster_count`
- `formal_opportunity_count`
- `final_recommendation_count`
- `formal_representative_codes`
- `risk_cluster_map`
- `independence_rationale`

必须区分：

```text
company_confirmed_count
```

与：

```text
formal_opportunity_count
```

前者是公司级研究结果数量；后者是去除共同主导风险因子后的正式独立机会数量。

---

## 12. 市场风险与执行覆盖

市场 `bearish / weak breadth / high risk` 只能影响最终估值、等待倾向和最终行动口径。

它不得：

- 改变程序候选全集；
- 跳过 Structured Screening；
- 修改已经 FROZEN 的研究集合；
- 改变 frozen `deep_read_codes`；
- 成为研究覆盖不完整的理由；
- 被用来绕过 Risk Cluster；
- 被用来在 coverage 未 COMPLETE 时生成正式榜。

---

## 13. 执行原则

> **一次任务触发，严格串行执行 Stage A → FROZEN Ledger Hard Gate → Stage B。**

> **Stage A 只做 repository-only Structured Screening；FROZEN 并回读验证之前不得使用公司级外部公开资料。**

> **Frozen Ledger v3 是可审计硬检查点：逐公司 entry 是真相，代码集合是派生索引。**

> **PEER_DOMINATED 只表达严格公司级支配，不承担行业/风险簇去重。**

> **研究层防漏，发布层去相关。**

> **Stage B 不重新做 Pre-Research，也不得修改 frozen deep_read_codes。**

> **任务完成的定义是穷尽 frozen deep_read_codes，不是找到足够多可以出榜的公司。**

> **Deep Research coverage 未 COMPLETE 时，没有正式独立机会榜。**

> **正式机会集合没有目标数量和固定上限；排名只表示优先级。**

> **程序资格不由模型重算。**

> **研究覆盖完整性和最终榜风险去重是两件不同的事。**
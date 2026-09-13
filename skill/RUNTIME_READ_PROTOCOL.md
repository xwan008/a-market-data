# A股低风险买点榜｜运行时执行协议

本文件是“A股低风险买点榜”的唯一执行契约。它定义正式输入、阶段边界、两个持久化检查点、写安全、断点恢复、Deep Research coverage 与正式发布硬门。

具体公司判断、Deep Research、估值、Risk Cluster Consolidation 与买点语义，以同一轮锁定的 `skill/SKILL.md` 为准。

---

## 1. 总体架构｜一个正式任务，Stage B 可断点续跑

系统始终只使用一个正式任务，不拆成多个 Automation。

首次进入某一套正式输入时：

```text
任务触发
↓
Stage A｜Structured Screening
repository-only
↓
research/pre_research_ledger.json
status = FROZEN
↓
回读 Frozen Ledger + 正式输入
↓
Frozen Ledger Hard Gate
↓
PASSED
↓
初始化 research/deep_research_ledger.json
status = BUILDING
↓
Stage B｜Deep Research
只研究 frozen deep_read_codes
↓
按 remaining_deep_research_codes 分批研究并持久化
↓
Deep Research coverage = COMPLETE
↓
Risk Cluster Consolidation
↓
正式独立机会榜
```

如果后续触发时存在可恢复的 Stage B checkpoint，则不重新执行 Stage A：

```text
任务触发
↓
验证 Frozen Pre-Research Ledger
+ Deep Research Ledger parent 绑定
+ trade_date
+ 五个正式输入 blob SHA
+ expected / actual / remaining 闭合
↓
全部一致
↓
直接从 remaining_deep_research_codes 继续 Stage B
```

因此真正的不变量是阶段顺序与证据边界，而不是“每次 invocation 都从 Stage A 重做”。

- Stage A 不做公司级外部 Deep Research；
- Stage B 不重新做 PEER_DOMINATED / CLEARLY_WEAK / PASS / UNCERTAIN；
- Stage B 不得修改 frozen `deep_read_codes`；
- Stage B 可以跨多个 invocation 继续，但只能在同一 parent、同一正式输入下恢复；
- 新 Stage A 一旦开始，旧 Stage B checkpoint 立即失效；
- coverage 未 COMPLETE 时不得发布正式榜。

---

## 2. 正式输入与正式检查点

### 2.1 正式输入

正式输入只有：

- `skill/RUNTIME_READ_PROTOCOL.md`
- `skill/SKILL.md`
- `data/runtime/meta.json`
- `meta.screening_group_file`
- `meta.candidate_file`

### 2.2 正式检查点

正式运行检查点只有：

- `research/pre_research_ledger.json`：Stage A 的完整 Structured Screening 结果与 frozen `deep_read_codes`；
- `research/deep_research_ledger.json`：Stage B 的可恢复研究进度、公司级终态结果与 coverage。

两者都不是市场数据源。Deep Research Ledger 必须严格绑定一个 FROZEN Pre-Research Ledger。

### 2.3 非正式输入

以下内容不得作为当前运行事实源：

- `peer_groups.json`
- `company_research_view.json`
- `data/runtime/details/`
- `data/runtime/screening_snapshot.json`
- `data/runtime/industry_state_compact.json`
- 历史 `deep_research_results_*`
- 旧榜单
- 未绑定当前 parent_run_id 的旧公司研究结果
- 其他临时 research 文件

历史结果只能人工复盘，不能自动带入新一轮。

---

## 3. Bootstrap 与 Runtime Hard Gate

在任何公司级外部 Web 研究、股票排名或正式榜输出之前，必须先完成执行身份确认。

每次触发先读取：

- 当前 `main`
- Protocol
- Skill
- `meta.json`
- `screening_group_file`
- `candidate_file`
- 两个 Ledger（若存在）

如果无法访问 GitHub、无法读取正式输入、或无法验证当前运行身份：

```text
EXECUTION_BOOTSTRAP_FAILED
```

立即停止。不得降级为“普通网页搜股”。

Runtime Hard Gate 任一失败则停止：

- `runtime_validation.status != "passed"`
- snapshot 不是当前应使用的最近有效 A 股正式收盘
- meta / screening / candidates 缺失或无法解析
- `screening_group_validation.status != "passed"`
- screening group 与 candidate 股票全集不一致
- YoY 单位不是 `percentage_points`

### 3.1 screening_group Consumer Contract

`screening_group_file` 是 Stage A 唯一正式工作视图。

当前视图是自描述、列式、行可寻址 JSON：

- `meta.screening_group_member_columns` 定义 member row 每一列语义；
- `meta.screening_group_serialization.line_count` 定义完整行数；
- `screening_group_validation.line_addressable == true` 表示允许按行区间读取。

如果一次整文件响应被接口截断，不得直接判定输入不可读；必须按有界行区间连续读取，直到覆盖 `1..line_count` 全部行并完整解析 JSON。

不得用 `candidate_file` 或部分 screening groups 替代未读取部分。只有完整覆盖全部 candidate member rows 后才能开始 Stage A 判断。

---

## 4. 程序筛选信任边界

程序已经确定：

- Eligibility Filter 结果；
- Eligibility audit；
- Structure Filter 结果；
- candidate code 唯一性；
- screening group code 唯一性与 exact match；
- `structure_tier / strong_support / strong_volume_zone`；
- `meta.structural_rule`；
- YoY 单位。

模型不得重新计算或推翻这些程序资格结论。

---

## 5. Stage A｜Structured Screening Freeze

### 5.1 锁定本轮输入

开始新的 Stage A 时：

1. 获取当前 `main` commit SHA，记录为 `source_runtime_commit_sha`；
2. 从该版本读取 Protocol、Skill、meta、screening_groups、candidates；
3. 记录五个正式 Git blob SHA：
   - `protocol_blob_sha`
   - `skill_blob_sha`
   - `meta_blob_sha`
   - `screening_group_blob_sha`
   - `candidate_blob_sha`
4. 生成唯一 `run_id`；
5. Stage A 后续只使用这套锁定结构化输入。

Ledger 写入会改变 main commit SHA，因此同一研究输入用五个 blob SHA 判断，不要求 current main SHA 等于 `source_runtime_commit_sha`。

### 5.2 新 Stage A 先使旧 Stage B checkpoint 失效

只要决定开始新的 Stage A，就必须先把现有 `research/deep_research_ledger.json` 标记为 `STALE`（若存在且非 EMPTY），并记录失效原因。

旧 Deep Research 结果从此不得计入新一轮 coverage。

### 5.3 Pre-Research Ledger 先写 BUILDING

开始 Model Prescreen 前，把：

```text
research/pre_research_ledger.json
```

写为本轮：

```text
status = BUILDING
run_id = <本轮唯一值>
```

同时写入五个正式 blob SHA、trade_date、candidate_count、信息边界字段，并清空四类集合、`deep_read_codes` 与 `ledger_entries`。

写入后必须回读确认：

- `status == BUILDING`
- `run_id` 一致
- 五个正式 blob SHA 一致

不一致则停止，防止并发覆盖。

### 5.4 Repository-only 信息边界

Stage A 可以访问 GitHub，但在 Pre-Research Ledger FROZEN 并通过 Hard Gate 之前，禁止搜索或读取：

- 公司官网
- 公司公告正文 / 交易所外部页面
- 新闻
- 券商研报
- 搜索引擎结果
- 行业网站
- 其他公司级外部公开资料

若发生越界：

```text
stage_a_information_boundary = VIOLATED
external_company_research_before_freeze = true
```

本轮 Pre-Research Ledger 必须 FAILED / 非 FROZEN，Deep Research coverage = UNVERIFIED，停止整轮。

### 5.5 完成全部 Model Prescreen

严格按 `SKILL.md` 对全部候选完成：

1. PEER_DOMINATED；
2. 未被支配者再进入 CLEARLY_WEAK / PASS_TO_DEEP_RESEARCH / UNCERTAIN。

每只候选必须恰好一个 `ledger_entry`。不得因为已有足够候选、想减少后续研究量、或预计正式榜已足够而停止。

PEER_DOMINATED 只能表达严格公司级支配，不得承担行业去重或 Risk Cluster 职责。

---

## 6. Frozen Pre-Research Ledger 契约

FROZEN Ledger 至少包含：

```json
{
  "status": "FROZEN",
  "run_id": "...",
  "created_at": "...",
  "source_runtime_commit_sha": "...",
  "protocol_blob_sha": "...",
  "skill_blob_sha": "...",
  "meta_blob_sha": "...",
  "screening_group_blob_sha": "...",
  "candidate_blob_sha": "...",
  "trade_date": "YYYY-MM-DD",
  "candidate_count": 0,
  "ledger_count": 0,
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

不维护历史 schema 版本号。当前 Protocol 就是唯一契约。

必须满足：

```text
deep_read_codes = pass_to_deep_research_codes ∪ uncertain_codes
```

```text
candidate_codes
= peer_dominated_codes
∪ clearly_weak_codes
∪ pass_to_deep_research_codes
∪ uncertain_codes
```

四集合互斥，且：

```text
ledger_count == candidate_count == ledger_entries_count
```

每个 entry 至少：

```json
{
  "code": "000000",
  "result": "PASS_TO_DEEP_RESEARCH",
  "reason_code": "...",
  "reason": "..."
}
```

PEER_DOMINATED entry 额外必须包含：

- `dominated_by`
- `price_structure_basis`
- `valuation_basis`
- `operating_basis`
- `differentiated_advantage_check`
- `uncertainty_check`

四个代码集合必须能由 entries 完整重建。

FROZEN 写入前再次回读当前 BUILDING Ledger，并确认 run_id 与五个 blob SHA 未被改变；写入必须使用当前 Ledger blob SHA。发现并发覆盖则停止。

---

## 7. Frozen Ledger Hard Gate 与 Stage B 恢复判定

### 7.1 Frozen Ledger Hard Gate

必须重新读取当前 Pre-Research Ledger 与五个正式输入，验证：

1. `status == FROZEN`
2. `repository_only == true`
3. `external_company_research_before_freeze == false`
4. `stage_a_information_boundary == CLEAN`
5. `ledger_count == candidate_count`
6. 四集合互斥且并集等于当前 candidate 全集
7. `deep_read_codes == PASS ∪ UNCERTAIN`
8. entries 完整且可重建四集合
9. PEER_DOMINATED 审计字段完整
10. trade_date 一致
11. candidate_count 一致
12. 当前 Protocol / Skill / meta / screening_groups / candidates 五个 blob SHA 与 Ledger 完全一致

任一失败：

```text
ledger_validation = FAILED
```

不得开始或恢复 Stage B，也不得生成正式榜。

通过后：

```text
expected_deep_research_codes = pre_research_ledger.deep_read_codes
```

从此不得增删 expected。

### 7.2 每次触发先判断是否可恢复 Stage B

只有同时满足以下条件，才允许跳过 Stage A、直接恢复 Stage B：

- 7.1 Hard Gate PASSED；
- Deep Research Ledger `status` 为 `BUILDING` 或 `COMPLETE`；
- `parent_run_id == pre_research_ledger.run_id`；
- `parent_pre_research_blob_sha` 等于当前 FROZEN Pre-Research Ledger 的 Git blob SHA；
- trade_date 一致；
- 五个正式输入 blob SHA 一致；
- expected 与当前 frozen `deep_read_codes` 集合完全一致；
- actual / remaining / company_results 可严格互相重建；
- 不存在 expected 之外的公司结果。

通过：

```text
resume_stage_b = true
```

只研究 remaining，已完成 company_results 不重新从零研究。

不通过：旧 Deep Research checkpoint 不得复用。如果 Pre-Research Ledger 也无法通过 Hard Gate，则重新执行 Stage A。

---

## 8. Stage B｜可恢复 Deep Research Ledger

### 8.1 顶层字段

`research/deep_research_ledger.json` 至少包含：

```json
{
  "status": "BUILDING",
  "parent_run_id": "...",
  "parent_pre_research_blob_sha": "...",
  "created_at": "...",
  "updated_at": "...",
  "trade_date": "YYYY-MM-DD",
  "protocol_blob_sha": "...",
  "skill_blob_sha": "...",
  "meta_blob_sha": "...",
  "screening_group_blob_sha": "...",
  "candidate_blob_sha": "...",
  "expected_deep_research_codes": [],
  "actual_deep_researched_codes": [],
  "remaining_deep_research_codes": [],
  "company_results": [],
  "checkpoint_count": 0
}
```

不维护历史 schema 版本号。

初始化：

```text
expected = frozen deep_read_codes
actual = ∅
remaining = expected
status = BUILDING
```

### 8.2 公司级完成结果

只有一家公司已完成足够公开资料核验、可以形成以下终态之一，才计入 actual：

- `confirmed`
- `waiting`
- `research_uncertain`
- `excluded`

每个 `company_result` 至少保留：

- `code`
- `status`
- `researched_at`
- `primary_business`
- `primary_profit_driver`
- `dominant_risk_factor`
- `forward_earnings_logic`
- `earnings_quality_and_normalization`
- `strongest_counterevidence`
- `valuation_summary`
- `sources`

`sources` 保存稳定、可复核的信息，例如：

- `title`
- `url`
- `published_at`
- `retrieved_at`

不得只保存一次 execution 内的临时搜索编号。

具体研究深度与估值语义由 `SKILL.md` 定义。

### 8.3 Checkpoint 批次

Stage B 使用小批量持久化，但批次只解决执行容量，不改变研究集合：

1. 从 `remaining_deep_research_codes` 继续；
2. 每完成最多 10 家新的公司级终态结果，回读当前 Deep Research Ledger；
3. 验证 parent / expected / 当前 Ledger blob 未发生冲突；
4. 使用当前 Ledger blob SHA 写入 checkpoint；
5. 更新 actual、remaining、company_results、checkpoint_count、updated_at；
6. 当前 invocation 仍有执行能力则继续下一批，不因为 checkpoint 主动停止；
7. 若无法在本次完成全部 remaining，结束前尽可能保存已形成终态的结果，并报告 INCOMPLETE。

“每批最多 10 家”不是 Top N、研究上限或推荐数量。

### 8.4 写安全

每次 checkpoint 写入前必须确认：

- `status == BUILDING`
- parent_run_id 未变化
- parent_pre_research_blob_sha 未变化
- expected 未变化
- 不存在 expected 之外的结果
- company code 唯一

如果并发执行已经新增了不冲突的完成结果，合并后继续 remaining；parent 或 expected 冲突则立即停止，禁止覆盖。

---

## 9. Deep Research coverage｜正式榜硬门

Deep Research Ledger 必须始终满足：

```text
expected = actual ∪ remaining
actual ∩ remaining = ∅
company_results[].code = actual
```

### COMPLETE

只有：

```text
expected == actual
remaining = ∅
company_results_count == expected_count
status = COMPLETE
```

才允许 Risk Cluster Consolidation 和正式榜。

### INCOMPLETE

只要 remaining 非空：

```text
deep_research_coverage = INCOMPLETE
```

允许输出 checkpoint 进度、公司状态计数、actual / remaining，但禁止把已完成子集包装成正式榜、临时榜、当前 Top N 或其他推荐名单。

下一次 invocation 若满足 7.2，必须直接从 remaining 继续，不重新执行 Stage A，也不重复研究 actual。

### UNVERIFIED

包括但不限于：

- Stage A 信息边界污染
- Frozen Pre-Research Ledger 无效
- Deep Research Ledger parent 无法验证
- expected / actual / remaining / company_results 不闭合
- 当前正式输入与 checkpoint blob 不一致
- 无法恢复 frozen `deep_read_codes`

此时不得发布正式榜，也不得复用旧 checkpoint。

任务完成的唯一定义仍是：

```text
deep_research_coverage = COMPLETE
```

---

## 10. Risk Cluster Consolidation｜发布层去相关

前置条件：

```text
deep_research_coverage == COMPLETE
```

只有公司级 Deep Research 全部闭合、估值完成后，才按 `SKILL.md` 做 Risk Cluster。

要求：

- 不改变 deep_read_codes；
- 不改变 actual_deep_researched_codes；
- 不改变公司级 confirmed / waiting / research_uncertain / excluded；
- 正式榜排名对象是独立风险收益机会；
- 同一风险簇默认一个 representative_code；
- 同簇其他有价值公司保留为 alternative_codes；
- 同行业存在多个独立机会时记录 independence_rationale；
- 不设目标数量、固定上限或 Top N 截断。

Risk Cluster 是发布层去相关，不是研究层淘汰。

---

## 11. 最终审计输出

正式输出至少包含：

### Stage A

- trade_date
- run_id
- candidate_count
- ledger_count
- peer_dominated_count
- company_clearly_weak_count
- pass_to_deep_research_count
- uncertain_prescreen_count
- deep_research_candidate_count
- ledger_entries_count
- stage_a_information_boundary
- ledger_status
- ledger_validation
- 五个正式输入 blob SHA

### Stage B

- parent_run_id
- deep_research_ledger_status
- checkpoint_count
- resume_stage_b
- expected_deep_research_count
- actual_deep_researched_count
- remaining_deep_research_count
- deep_research_coverage
- company_confirmed_count
- waiting_count
- research_uncertain_count
- excluded_count
- actual_deep_researched_codes
- remaining_deep_research_codes

### 程序漏斗

- snapshot.trade_date
- universe_count
- source_candidate_count
- Eligibility 各互斥排除原因数量
- structural_relevance_count
- screening_group_count

只有 coverage COMPLETE 时再发布：

- risk_cluster_count
- formal_opportunity_count
- final_recommendation_count
- formal_representative_codes
- risk_cluster_map
- independence_rationale

必须区分 `company_confirmed_count` 与 `formal_opportunity_count`。

---

## 12. 市场风险与执行覆盖

`bearish / weak breadth / high risk` 只能影响最终估值、等待倾向与行动口径。

它不得：

- 改变程序候选全集；
- 跳过 Structured Screening；
- 修改 frozen deep_read_codes；
- 修改 Stage B expected；
- 成为 coverage 不完整的理由；
- 在 coverage 未 COMPLETE 时生成正式榜。

---

## 13. 执行原则

> **一个正式任务管理全流程；Stage A 只在没有可恢复 checkpoint 或正式输入变化时重新执行。**

> **Stage A 只做 repository-only Structured Screening；FROZEN 并回读验证之前不得使用公司级外部公开资料。**

> **Frozen Pre-Research Ledger 是 Stage A 的可审计硬检查点：逐公司 entry 是真相，代码集合是派生索引。**

> **Deep Research Ledger 是 Stage B 的可恢复硬检查点：company_results 是真相，actual / remaining 是派生集合。**

> **PEER_DOMINATED 只表达严格公司级支配，不承担行业/风险簇去重。**

> **研究层防漏，发布层去相关。**

> **Stage B 不重新做 Pre-Research，也不得修改 frozen deep_read_codes。**

> **任务完成的定义是穷尽 frozen deep_read_codes，不是找到足够多可以出榜的公司。**

> **Deep Research coverage 未 COMPLETE 时，没有正式独立机会榜。**

> **Checkpoint 批次只是持久化机制，不是研究上限、Top N 或推荐数量。**

> **程序资格不由模型重算。**
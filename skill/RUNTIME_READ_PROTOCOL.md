# A股低风险买点榜｜运行时执行协议

本文件是“A股低风险买点榜”的唯一执行契约。它定义正式输入、单次触发阶段边界、Frozen Pre-Research Ledger、Deep Research coverage 与正式发布硬门。

具体公司判断、Deep Research、估值、Risk Cluster Consolidation 与买点语义，以同一轮锁定的 `skill/SKILL.md` 为准。

---

## 1. 总体架构｜每次触发必须一步到位

每一次 07:00、19:00 或手动触发，都是一个**全新的、不可跨 invocation 续跑的完整研究事务**。

```text
任务触发
↓
锁定当前正式 runtime / Protocol / Skill
↓
完整消费 screening_group_file
↓
Stage A｜Structured Screening
repository-only
按完整申万三级行业组做同一 invocation 内批处理
↓
109/109（或当轮 candidate_count/candidate_count）
↓
research/pre_research_ledger.json
status = FROZEN
↓
回读 Frozen Ledger + 五个正式输入
↓
Frozen Ledger Hard Gate
↓
PASSED
↓
Stage B｜Deep Research
本次 invocation 内穷尽 frozen deep_read_codes
↓
expected == actual
↓
Deep Research coverage = COMPLETE
↓
Risk Cluster Consolidation
↓
正式“A股低风险买点榜”
```

核心不变量：

- **每次触发都从 Stage A 开始。**不得读取上一轮 FROZEN Ledger 作为本轮 Stage A 结果；
- Stage A 不做公司级外部 Deep Research；
- Stage A execution batch 只用于降低单次模型负担，不得改变同行比较语义、判断标准或候选全集；
- Stage A 的申万三级行业组不可拆分到不同 execution batch；
- Stage A 部分批次结果不得写成 FROZEN Ledger，也不得供下一次 invocation 续跑；
- Stage B 不重新做 PEER_DOMINATED / CLEARLY_WEAK / PASS / UNCERTAIN；
- Stage B 不得修改本轮 frozen `deep_read_codes`；
- **Stage B 研究结果只属于当前 invocation，不建立跨 invocation 的 Deep Research checkpoint，不读取上一轮公司研究结果续跑；**
- 本次触发只有两种结束：`COMPLETE + 正式榜`，或 `FAILED/INCOMPLETE + 无正式榜`；
- “Stage A 本轮处理一部分、下次继续”以及“Deep Research 本轮研究一部分、下次继续”都不是合法正常执行模式。

---

## 2. 正式输入与唯一阶段检查点

### 2.1 正式输入

正式输入只有：

- `skill/RUNTIME_READ_PROTOCOL.md`
- `skill/SKILL.md`
- `data/runtime/meta.json`
- `meta.screening_group_file`
- `meta.candidate_file`

### 2.2 唯一正式阶段检查点

正式阶段检查点只有：

- `research/pre_research_ledger.json`

它只用于**同一次 invocation 内**证明 Stage A 已完整结束并允许 Stage B 开始。

它不是跨轮缓存。下一次任务触发必须先生成新的 `run_id`，把该文件写成新的 `BUILDING`，使上一轮 FROZEN 结果立即失效。

### 2.3 明确不存在 Stage A / Stage B 跨轮续存入口

当前正式运行**不存在**以下机制：

- Stage A partial ledger 跨 invocation 恢复
- 上一轮 Stage A 已处理公司跳过本轮判断
- `research/deep_research_ledger.json`
- `resume_stage_b`
- `parent_run_id`
- `remaining_deep_research_codes` 跨 invocation 恢复
- 上一轮 `company_results` 自动复用
- 上一轮已研究公司跳过本轮研究

任何历史 Stage A / Deep Research 结果、旧榜单、旧公司研究结论只能人工复盘，不得作为本轮事实输入。

---

## 3. Bootstrap 与 Runtime Hard Gate

在任何公司级外部 Web 研究、股票排名或正式榜输出之前，必须先完成执行身份确认。

每次触发必须读取：

- 当前 `main`
- Protocol
- Skill
- `meta.json`
- `screening_group_file`
- `candidate_file`

不得读取历史公司研究结果来替代本轮 Stage B。

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

### 3.1 screening_group Consumer Contract｜固定区间读取

`screening_group_file` 是 Stage A 唯一正式模型工作视图。

当前视图是自描述、列式、行可寻址 JSON：

- `meta.screening_group_member_columns` 定义 member row 每一列语义；
- `meta.screening_group_serialization.line_count` 定义完整行数；
- `screening_group_validation.line_addressable == true` 表示允许按行区间读取。

当 `line_addressable == true` 时，正式消费路径**不得依赖一次整文件响应是否完整**。必须直接按固定区间读取：

```text
chunk_size = 40 lines
range_1 = 1..40
range_2 = 41..80
...
range_n = ...line_count
```

例如 `line_count = 646` 时，正式读取计划固定为：

```text
1..40
41..80
81..120
121..160
161..200
201..240
241..280
281..320
321..360
361..400
401..440
441..480
481..520
521..560
561..600
601..640
641..646
```

要求：

1. 每个区间必须显式使用 `start_line / end_line`；
2. 必须覆盖 `1..line_count`，不得有 gap；
3. 不得重复区间来替代缺失区间；
4. 全部区间读取完成后才能开始 Stage A 判断；
5. 如果某个有界区间本身读取失败，应对**该区间**重试；只有有界区间持续不可读或连接器明确报错，才允许判定输入读取失败；
6. 一次整文件响应截断本身不是失败理由，也不得触发 STOPPED_EARLY。

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

### 5.1 每次触发无条件建立新 run

每次任务触发：

1. 获取当前 `main` commit SHA，记录为 `source_runtime_commit_sha`；
2. 从该版本读取 Protocol、Skill、meta、screening_groups、candidates；
3. 记录五个正式 Git blob SHA：
   - `protocol_blob_sha`
   - `skill_blob_sha`
   - `meta_blob_sha`
   - `screening_group_blob_sha`
   - `candidate_blob_sha`
4. 生成新的唯一 `run_id`；
5. 无论上一轮 Ledger 是 FROZEN / FAILED / STALE，都不得直接复用，必须写成本轮 `BUILDING`。

Ledger 写入会改变 main commit SHA，因此本轮一致性使用五个正式文件的 blob SHA 判断，不要求 current main SHA 等于 `source_runtime_commit_sha`。

### 5.2 Pre-Research Ledger 先写 BUILDING

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

### 5.3 Repository-only 信息边界

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

本轮 Ledger 必须 FAILED / 非 FROZEN，Deep Research coverage = UNVERIFIED，停止整轮。

### 5.4 Stage A｜完整行业组原子化批处理

严格按 `SKILL.md` 对全部候选完成：

1. PEER_DOMINATED；
2. 未被支配者再进入 CLEARLY_WEAK / PASS_TO_DEEP_RESEARCH / UNCERTAIN。

为了避免一次性对全部候选做单块模型判断，Stage A 必须在**同一次 invocation 内**采用 execution batch，但批次只能解决执行负担，不能改变投资语义。

#### 5.4.1 批次原子单位

Stage A 的最小不可拆分单位是：

```text
一个完整申万三级行业 screening group
```

同一 screening group 的所有候选必须在同一个 Stage A batch 中一起判断，禁止把同组候选拆到不同 batch，否则无法形成合法的 PEER_DOMINATED 同行判断。

#### 5.4.2 确定性打包规则

按 `screening_group_file` 中 groups 的原始顺序遍历，使用：

```text
target_batch_candidate_count = 20
```

确定性构建批次：

1. 当前 batch 为空时，直接加入下一个完整 screening group；
2. 当前 batch 非空，若加入下一个完整 group 后候选数将 `> 20`，先关闭当前 batch，再从该 group 开启下一 batch；
3. screening group 永远不拆分；
4. 如果未来出现单一 group 自身 `> 20`，仍以 group 完整性优先，该 group 单独构成一个 batch；
5. 不得根据候选质量、行业偏好、预期结果或模型主观判断调整 batch 边界。

因此 batch 是由正式输入顺序和 group size 唯一确定的执行容器。

#### 5.4.3 每批处理要求

每个 Stage A batch 必须：

1. 对 batch 内每个完整 screening group 按 `SKILL.md` 完成同行支配判断；
2. 对未被支配公司完成绝对质量判断；
3. 为 batch 内每只候选形成且仅形成一个临时 `ledger_entry`；
4. batch 内不得 Top N、不得配额、不得因为本批已有足够 PASS/UNCERTAIN 就降低其他公司状态；
5. batch 完成后立即进入下一 batch，不得主动结束本轮。

批次完成结果仅存在于**当前 invocation 内存**。不得把部分 `ledger_entries` 写入正式 FROZEN Ledger，也不得创建可供下一次 invocation 恢复的 Stage A checkpoint。

#### 5.4.4 Stage A 完成硬门

只有所有 Stage A batches 完成，并满足：

```text
stage_a_processed_count == candidate_count
```

且：

```text
unique(stage_a_processed_codes) == candidate_codes
```

且每只候选恰好一个 `ledger_entry`，才允许进入 FROZEN 写入。

随后一次性从全部临时 entries 派生：

- `peer_dominated_codes`
- `clearly_weak_codes`
- `pass_to_deep_research_codes`
- `uncertain_codes`
- `deep_read_codes`

不得因为已有足够候选、想减少后续研究量、或预计正式榜已足够而停止。

PEER_DOMINATED 只能表达严格公司级支配，不得承担行业去重或 Risk Cluster 职责。

如果同一 invocation 在 Stage A 全覆盖前结束，则本轮 Stage A = FAILED；不得冻结部分 Ledger，不得在下一轮复用已完成 batch。

### 5.5 Stage A Diagnostic Probe

`research/last_execution_probe.json` 是 diagnostic-only telemetry，不是正式输入，不得用于续跑或恢复任何 Stage A 结果。

进入 Stage A 后至少记录：

- `phase = "STAGE_A_MODEL_PRESCREEN"`
- `stage_a_expected_count = candidate_count`
- `stage_a_processed_count`
- `stage_a_batch_index`
- `stage_a_batch_count`
- `stage_a_current_group_codes`
- `stage_a_last_completed_group`
- `stage_a_last_completed_code`
- `tool_error`

规则：

1. 每个 Stage A batch 开始前更新 `stage_a_batch_index` 与当前 group 范围；
2. 每个 batch 完成后更新累计 `stage_a_processed_count`、last completed group/code，然后立即进入下一 batch；
3. 这些字段只记录进度，不保存部分公司判断结果；
4. 如果模型在无真实工具/系统错误时、`stage_a_processed_count < stage_a_expected_count` 主动结束，probe 必须写：

```text
status = STOPPED_EARLY
termination_reason = MODEL_TERMINATED_BEFORE_STAGE_A_COVERAGE
```

5. 如果发生可观察的工具错误，写 `TOOL_ERROR` 与具体 `tool_error`；
6. 如果系统硬中止且来不及写最终失败状态，probe 可能停留 `RUNNING` 且 `stage_a_processed_count < stage_a_expected_count`，仅用于人工诊断，下一次仍必须从新 Stage A 开始。

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

每个 entry 至少包含：

- `code`
- `result`
- `reason_code`
- `reason`

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

## 7. Frozen Ledger Hard Gate

Stage A 写入 FROZEN 后，不得凭内存直接进入 Stage B。

必须重新读取当前 Pre-Research Ledger 与五个正式输入，验证：

1. `status == FROZEN`
2. `run_id` 与本次 invocation 的 Stage A run_id 一致
3. `repository_only == true`
4. `external_company_research_before_freeze == false`
5. `stage_a_information_boundary == CLEAN`
6. `ledger_count == candidate_count`
7. 四集合互斥且并集等于当前 candidate 全集
8. `deep_read_codes == PASS ∪ UNCERTAIN`
9. entries 完整且可重建四集合
10. PEER_DOMINATED 审计字段完整
11. trade_date 一致
12. candidate_count 一致
13. 当前 Protocol / Skill / meta / screening_groups / candidates 五个 blob SHA 与 Ledger 完全一致

任一失败：

```text
ledger_validation = FAILED
```

整轮停止，不得开始公司级外部研究，不得生成正式榜。

通过后：

```text
expected_deep_research_codes = pre_research_ledger.deep_read_codes
```

从此本轮不得增删 expected。

---

## 8. Stage B｜单次 invocation 穷尽 Deep Research

### 8.1 禁止跨轮复用

Stage B 唯一研究集合是本轮 Frozen Ledger 的：

```text
expected_deep_research_codes
```

Stage B 的公司级结论保存在**本次执行上下文**中，不写入供下一轮恢复的正式 checkpoint。

禁止：

- 读取上一轮公司研究结论作为本轮完成结果；
- 因为某公司上一轮已研究就跳过；
- 从上一轮 actual / remaining 继续；
- 把旧公司状态计入本轮 `actual_deep_researched_codes`；
- 因为已经找到若干 confirmed 就停止；
- 因市场风险高而缩小 expected。

### 8.2 本轮公司级终态

只有一家公司在**本次 invocation**完成足够公开资料核验、可以形成以下终态之一，才计入本轮 actual：

- `confirmed`
- `waiting_for_entry`
- `research_uncertain`
- `excluded`

`waiting` 只作为历史结果的 legacy alias；新运行统一输出 `waiting_for_entry`。

每家公司本轮至少形成：

- `code`
- `status`
- `primary_business`
- `primary_profit_driver`
- `dominant_risk_factor`
- `forward_earnings_logic`
- `earnings_quality_and_normalization`
- `strongest_counterevidence`
- `valuation_summary`
- `sources`

具体研究深度、估值与安全区语义由 `SKILL.md` 定义。

### 8.3 一步到位的执行策略

为了在一次触发内完成全部 expected，Stage B 必须采用**批量优先、覆盖优先**的研究方式，而不是一家公司一次搜索、一家公司一次工具调用的完全串行方式。

Stage B execution batch 固定为：

```text
batch_size = 12 companies
order = frozen deep_read_codes 的既定顺序
```

最后一批可以少于 12 家。不得根据行业、真实业务、共享主导变量、候选质量或预期结论重新排序或重组 execution batch。行业、真实主营和共享主导变量只用于选择分析框架与复用公共证据，不改变 batch 边界。

执行要求：

1. 严格保持上述 frozen 顺序与固定 batch 边界；
2. 同一工具调用中尽可能批量发起多个独立公司查询；
3. 公司自己的最新财报 / 业绩公告 / 交易所披露必须逐公司确认；
4. 同行业或同主导变量的公共行业证据可以一次获取后映射到多家公司，避免重复搜索；
5. runtime / candidate_file 已有的确定性价格、估值、财务字段直接使用，不重新去网页重复搜同一事实；
6. 对资料清楚的公司快速形成终态；只有出现业务异质、一次性收益、周期失真、来源冲突时才追加更深检索；
7. 研究过程中持续维护本轮内存集合 `actual_deep_researched_codes`，但**不得因为达到任何中间数量而结束**；
8. 必须继续直到 expected 全部形成终态或发生明确硬失败。

### 8.4 最低证据要求

“Deep Research”不等于机械要求每家公司搜索很多网站，但也不能只凭一个低质量二手页面完成全部判断。

每家公司至少需要：

- 一项可核验的公司级主要公开依据，优先最新财报、业绩公告、交易所/公司正式披露；
- 对 `primary_profit_driver` / `dominant_risk_factor` 的证据支持；该证据可以是公司披露，也可以是对同一驱动变量的共享行业证据；
- 至少一条能够推翻当前判断的 `strongest_counterevidence`。

多个网站转载同一份公告只算同一个原始证据，不因为 URL 数量增加而提高证据等级。

---

## 9. Deep Research coverage｜单次触发正式榜硬门

本轮维护：

- `expected_deep_research_codes`
- `actual_deep_researched_codes`
- 本轮公司级研究结果

只有本次 invocation 中完成足以形成公司级终态的公司，才计入 actual。

### COMPLETE

只有：

```text
expected_deep_research_codes == actual_deep_researched_codes
```

并且每个 expected code 都有唯一公司级终态结果，才允许：

```text
deep_research_coverage = COMPLETE
```

随后进入 Risk Cluster Consolidation 和正式榜。

### INCOMPLETE / FAILED

只要本次 invocation 结束时还有任何 expected code 没有形成终态：

```text
deep_research_coverage = INCOMPLETE
```

本次任务视为失败，不发布正式榜。

必须列出：

- `missing_deep_research_codes`
- `unexpected_researched_codes`（如有）
- `hard_failure_reason`（如果存在工具、连接、身份冲突或系统硬失败）

**INCOMPLETE 不产生可供下一次任务续跑的正式研究状态。下一次触发重新从 Stage A 开始。**

不得把已完成子集包装成正式榜、临时榜、当前 Top N 或其他推荐名单。

### UNVERIFIED

包括但不限于：

- Stage A 信息边界污染
- Frozen Pre-Research Ledger 无效
- expected 无法从本轮 frozen `deep_read_codes` 恢复
- 当前正式输入与本轮 Ledger blob 不一致
- coverage 集合无法验证

UNVERIFIED 同样不发布正式榜。

---

## 10. Risk Cluster Consolidation｜发布层去相关

前置条件：

```text
deep_research_coverage == COMPLETE
```

只有公司级 Deep Research 全部闭合、估值完成后，才按 `SKILL.md` 做 Risk Cluster。

要求：

- 不改变 `deep_read_codes`；
- 不改变 `actual_deep_researched_codes`；
- 不改变公司级 confirmed / waiting_for_entry / research_uncertain / excluded；
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

- `trade_date`
- `run_id`
- `candidate_count`
- `ledger_count`
- `peer_dominated_count`
- `company_clearly_weak_count`
- `pass_to_deep_research_count`
- `uncertain_prescreen_count`
- `deep_research_candidate_count`
- `ledger_entries_count`
- `stage_a_expected_count`
- `stage_a_processed_count`
- `stage_a_batch_index`
- `stage_a_batch_count`
- `stage_a_last_completed_group`
- `stage_a_information_boundary`
- `ledger_status`
- `ledger_validation`
- 五个正式输入 blob SHA

### Stage B

- `expected_deep_research_count`
- `actual_deep_researched_count`
- `deep_research_coverage`
- `company_confirmed_count`
- `waiting_for_entry_count`
- `research_uncertain_count`
- `excluded_count`
- `actual_deep_researched_codes`
- `missing_deep_research_codes`

### 程序漏斗

- `snapshot.trade_date`
- `universe_count`
- `source_candidate_count`
- Eligibility 各互斥排除原因数量
- `structural_relevance_count`
- `screening_group_count`

只有 coverage COMPLETE 时再发布：

- `risk_cluster_count`
- `formal_opportunity_count`
- `formal_representative_codes`
- `risk_cluster_map`
- `independence_rationale`

必须区分 `company_confirmed_count` 与 `formal_opportunity_count`。

---

## 12. 市场风险与执行覆盖

`bearish / weak breadth / high risk` 只能影响最终估值、等待倾向与行动口径。

它不得：

- 改变程序候选全集；
- 跳过 Structured Screening；
- 修改 Stage A batch 边界；
- 修改 frozen `deep_read_codes`；
- 修改 Stage B expected；
- 成为 coverage 不完整的理由；
- 在 coverage 未 COMPLETE 时生成正式榜。

---

## 13. 执行原则

> **每次任务触发都是一个全新、一步到位的完整事务；不得跨 invocation 续跑 Stage A 或公司研究。**

> **每次触发都从新的 Stage A 开始，上一轮 FROZEN Ledger 不得直接复用。**

> **screening_group_file 使用确定性的有界行区间完整消费，不把整文件截断交给模型自由解释。**

> **Stage A 按完整申万三级行业组原子化分批；batch 只降低执行负担，不改变同行比较、公司状态或候选全集。**

> **Stage A 只有当 processed == candidate_count 时才允许一次性 FROZEN；部分 batch 不形成正式 Ledger，也不供下一轮恢复。**

> **Stage A 只做 repository-only Structured Screening；FROZEN 并回读验证之前不得使用公司级外部公开资料。**

> **Frozen Pre-Research Ledger 只是在同一次 invocation 内连接 Stage A 与 Stage B 的可审计硬检查点。**

> **不存在正式 Deep Research Ledger，不存在 resume_stage_b，不读取上一轮 company_results。**

> **PEER_DOMINATED 只表达严格公司级支配，不承担行业/风险簇去重。**

> **研究层防漏，发布层去相关。**

> **Stage B 必须在本次 invocation 内穷尽 frozen deep_read_codes。**

> **任务完成的定义是当轮 expected == actual，不是找到足够多可以出榜的公司。**

> **Deep Research coverage 未 COMPLETE 时，本次任务失败且没有正式独立机会榜。**

> **程序资格不由模型重算。**
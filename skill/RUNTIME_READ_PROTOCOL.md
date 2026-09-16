# A股低风险买点榜｜运行时执行协议

本文件是“A股低风险买点榜”的唯一执行契约。它定义正式输入、单次触发阶段边界、Frozen Pre-Research Ledger、Stage B Gate、Deep Research coverage 与正式发布硬门。

具体公司判断、Gate 规则、Deep Research、估值、Risk Cluster Consolidation 与买点语义，以同一轮锁定的 `skill/SKILL.md` 为准。

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
candidate_count / candidate_count
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
Stage B｜Research Worthiness Gate
对 frozen deep_read_codes 全量处理
Q1 → Q2 → 必要时 Q2-lite
↓
gate coverage = COMPLETE
↓
派生 deep_research_required_codes
并标记 HIGH / LOW research priority
↓
Stage B｜Deep Research
本次 invocation 内穷尽 deep_research_required_codes
↓
expected_deep_research == actual_deep_researched
↓
Deep Research coverage = COMPLETE
↓
Stage B coverage = COMPLETE
↓
Risk Cluster Consolidation
↓
正式“A股低风险买点榜”
```

核心不变量：

- **每次触发都从 Stage A 开始。**不得读取上一轮 FROZEN Ledger 作为本轮 Stage A 结果；
- Stage A 不做公司级外部 Deep Research；
- Stage A execution batch 只用于降低单次模型负担，不改变同行比较语义、判断标准或候选全集；
- Stage A 申万三级行业组不可拆分到不同 execution batch；
- Stage A 部分批次结果不得写成 FROZEN Ledger，也不得供下一次 invocation 续跑；
- Stage B 不重新做 PEER_DOMINATED / CLEARLY_WEAK / PASS / UNCERTAIN；
- Stage B 不得修改本轮 frozen `deep_read_codes`，但必须按照 `SKILL.md` 从中派生 Gate-filtered 与 `deep_research_required_codes`；
- Gate-filtered 不是完整 Deep Research 四终态；
- Stage B Gate 和 Deep Research 结果都只属于当前 invocation，不建立跨 invocation checkpoint，不读取上一轮公司研究结果续跑；
- **正常控制流只有一个完成出口：`COMPLETE + 正式榜`。** `FAILED / INCOMPLETE / UNVERIFIED` 只用于发生可举证、不可恢复的客观硬失败后的审计，不是模型可自主选择的结束分支；
- “Stage A 本轮处理一部分、下次继续”“Gate 本轮处理一部分、下次继续”“Deep Research 本轮研究一部分、下次继续”都不是合法正常执行模式；
- 在没有客观硬失败时，只要 coverage 尚未闭合，模型的唯一合法动作就是继续当前流程的下一批，不得生成用户可见收尾回复。

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

### 2.3 明确不存在跨轮续存入口

当前正式运行不存在：

- Stage A partial ledger 跨 invocation 恢复；
- 上一轮 Stage A 已处理公司跳过本轮判断；
- `research/deep_research_ledger.json`；
- `resume_stage_b`；
- `parent_run_id`；
- Gate / Deep Research remaining codes 跨 invocation 恢复；
- 上一轮 company results 自动复用；
- 上一轮已研究公司跳过本轮研究。

历史 Stage A / Gate / Deep Research 结果、旧榜单、旧公司研究结论只能人工复盘，不得作为本轮正式事实输入。

---

## 3. Bootstrap 与 Runtime Hard Gate

在任何公司级外部 Web 研究、股票排名或正式榜输出之前，必须先完成执行身份确认。

每次触发必须读取：

- 当前 `main`；
- Protocol；
- Skill；
- `meta.json`；
- `screening_group_file`；
- `candidate_file`。

不得读取历史公司研究结果来替代本轮 Stage B。

如果无法访问 GitHub、无法读取正式输入、或无法验证当前运行身份：

```text
EXECUTION_BOOTSTRAP_FAILED
```

这是客观硬失败，立即停止。不得降级为普通网页搜股。

Runtime Hard Gate 任一失败属于客观硬失败并停止：

- `runtime_validation.status != "passed"`；
- snapshot 不是当前应使用的最近有效 A 股正式收盘；
- meta / screening / candidates 缺失或无法解析；
- `screening_group_validation.status != "passed"`；
- screening group 与 candidate 股票全集不一致；
- YoY 单位不是 `percentage_points`。

### 3.1 screening_group Consumer Contract｜固定区间读取

`screening_group_file` 是 Stage A 唯一正式模型工作视图。

当前视图是自描述、列式、行可寻址 JSON：

- `meta.screening_group_member_columns` 定义 member row 每列语义；
- `meta.screening_group_serialization.line_count` 定义完整行数；
- `screening_group_validation.line_addressable == true` 表示允许按行区间读取。

当 `line_addressable == true` 时，正式消费路径不得依赖一次整文件响应是否完整，必须按：

```text
chunk_size = 40 lines
range_1 = 1..40
range_2 = 41..80
...
range_n = ...line_count
```

要求：

1. 每个区间显式使用 `start_line / end_line`；
2. 覆盖 `1..line_count`，不得有 gap；
3. 不得重复区间替代缺失区间；
4. 全部区间读取完成后才能开始 Stage A 判断；
5. 某个有界区间读取失败，只重试该区间；只有持续不可读或连接器明确报错，才允许判定输入读取失败；
6. 一次整文件响应截断本身不是失败理由，也不得成为任务结束理由。

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
5. 无论上一轮 Ledger 是 FROZEN / FAILED / STALE，都必须写成本轮 `BUILDING`。

Ledger 写入会改变 main commit SHA，因此本轮一致性使用五个正式文件 blob SHA 判断，不要求 current main SHA 等于 `source_runtime_commit_sha`。

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

写入后必须回读确认 status、run_id、五个 blob SHA 全部一致。若不一致，视为并发覆盖客观硬失败并停止。

### 5.3 Repository-only 信息边界

Stage A 可以访问 GitHub，但在 Pre-Research Ledger FROZEN 并通过 Hard Gate 之前，禁止搜索或读取公司官网、公告正文/交易所外部页面、新闻、券商研报、搜索引擎结果、行业网站、其他公司级外部公开资料。

若发生越界：

```text
stage_a_information_boundary = VIOLATED
external_company_research_before_freeze = true
```

这是客观协议违规；本轮 Ledger 必须 FAILED / 非 FROZEN，Stage B coverage = UNVERIFIED，停止整轮。

### 5.4 Stage A｜完整行业组原子化批处理

严格按 `SKILL.md` 对全部候选完成：

1. PEER_DOMINATED；
2. 未被支配者再进入 CLEARLY_WEAK / PASS_TO_DEEP_RESEARCH / UNCERTAIN。

Stage A 必须在同一次 invocation 内采用 execution batch，但批次只解决执行负担。

最小不可拆分单位：

```text
一个完整申万三级行业 screening group
```

确定性打包规则：

```text
target_batch_candidate_count = 20
```

按 screening groups 原始顺序遍历：

1. 当前 batch 为空时加入下一个完整 group；
2. 当前 batch 非空，若加入下一个完整 group 后候选数 `> 20`，先关闭当前 batch；
3. group 永远不拆分；
4. 单一 group 自身 `> 20` 时，该 group 单独构成一个 batch；
5. 不得根据候选质量、行业偏好、预期结果或模型主观判断调整 batch 边界。

每个 Stage A batch 必须：

- 对完整 screening group 完成同行支配判断；
- 对未被支配公司完成绝对质量判断；
- 为每只候选形成且仅形成一个临时 `ledger_entry`；
- 不得 Top N、不得配额、不得因为已有足够 PASS/UNCERTAIN 就降低其他公司状态；
- batch 完成后立即进入下一 batch，不得主动结束。

批次结果只存在当前 invocation 内存，不得把部分 `ledger_entries` 写成正式 FROZEN Ledger，也不得供下一轮恢复。

### 5.5 Stage A 完成硬门

只有所有 Stage A batches 完成，并满足：

```text
stage_a_processed_count == candidate_count
unique(stage_a_processed_codes) == candidate_codes
```

且每只候选恰好一个 `ledger_entry`，才允许 FROZEN。

随后一次性派生：

- `peer_dominated_codes`
- `clearly_weak_codes`
- `pass_to_deep_research_codes`
- `uncertain_codes`
- `deep_read_codes`

不得因为已有足够候选、想减少 Stage B 数量、或预计正式榜已足够而停止。

### 5.6 Stage A Diagnostic Probe

`research/last_execution_probe.json` 是 diagnostic-only telemetry，不是正式输入，不得用于续跑。

进入 Stage A 后至少记录：

- `phase = "STAGE_A_MODEL_PRESCREEN"`
- `stage_a_expected_count`
- `stage_a_processed_count`
- `stage_a_batch_index`
- `stage_a_batch_count`
- `stage_a_current_group_codes`
- `stage_a_last_completed_group`
- `stage_a_last_completed_code`
- `tool_error`

**模型没有主动 `STOPPED_EARLY` 的控制权。** 在没有客观硬失败时，即使 Stage A coverage 尚未闭合，也不得写入“模型主动终止”类状态或原因；唯一合法动作是继续下一 Stage A batch。

若宿主平台在模型控制之外强制中断 invocation，该事实只能由平台级日志或后验外部审计记录；模型不得预判、模拟或主动写出 `MODEL_TERMINATED_*` 作为收尾理由。

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

每个 entry 至少包含 `code / result / reason_code / reason`。

PEER_DOMINATED entry 额外必须包含 `dominated_by / price_structure_basis / valuation_basis / operating_basis / differentiated_advantage_check / uncertainty_check`。

FROZEN 写入前再次回读当前 BUILDING Ledger，确认 run_id 与五个 blob SHA 未改变；写入必须使用当前 Ledger blob SHA。发现并发覆盖属于客观硬失败并停止。

---

## 7. Frozen Ledger Hard Gate

Stage A 写入 FROZEN 后，不得凭内存直接进入 Stage B。

必须重新读取当前 Pre-Research Ledger 与五个正式输入，验证：

1. `status == FROZEN`
2. `run_id` 与本次 invocation 一致
3. `repository_only == true`
4. `external_company_research_before_freeze == false`
5. `stage_a_information_boundary == CLEAN`
6. `ledger_count == candidate_count`
7. 四集合互斥且并集等于 candidate 全集
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

这是客观硬失败；整轮停止，不得开始公司级外部研究，不得生成正式榜。

通过后定义：

```text
expected_stage_b_codes = pre_research_ledger.deep_read_codes
```

从此本轮不得增删 `expected_stage_b_codes`。

注意：

> **`expected_stage_b_codes` 是 Stage B 候选全集，不等于最终必须做完整 Deep Research 的集合。`expected_deep_research_codes` 必须等 Stage B Gate 完整覆盖后再派生。**

### 7.1 PASSED → Gate Batch 1 原子迁移

一旦 Frozen Ledger Hard Gate = `PASSED`：

1. 唯一合法的下一阶段动作是构造并执行 `Gate Batch 1`；
2. 在 `gate_processed_count > 0` 之前，不得写 FAILED / INCOMPLETE / STOPPED_EARLY，不得生成阶段总结，不得评估剩余工作量，不得输出用户可见收尾回复；
3. 只有在 Hard Gate 通过后的下一实际工具/数据动作本身发生可举证且不可恢复的客观硬失败时，才允许进入失败审计；
4. 候选数量、预计耗时、上下文长度、剩余 Deep Research 数量、是否“看起来做不完”均不是失败事件。

---

## 8. Stage B｜Gate 全覆盖 + 子集完整 Deep Research

### 8.1 禁止跨轮复用

Stage B 唯一候选集合是本轮 Frozen Ledger 派生的：

```text
expected_stage_b_codes
```

Gate 与 Deep Research 结论保存在本次执行上下文，不写入供下一轮恢复的正式 checkpoint。

禁止：

- 读取上一轮公司研究结论作为本轮完成结果；
- 因某公司上一轮已研究就跳过；
- 从上一轮 actual / remaining 继续；
- 因为已经找到若干 confirmed 就停止；
- 因市场风险高而缩小 expected_stage_b_codes；
- 因预计公司太多、耗时太长或后续研究量过大而结束任务。

### 8.2 Stage B Research Worthiness Gate｜必须覆盖全部 frozen codes

严格按 `SKILL.md 4.0` 对 `expected_stage_b_codes` 逐只完成 Q1 / Q2 / 必要时 Q2-lite。

Gate 只允许派生互斥集合：

```text
gate_filtered_q1_codes
gate_filtered_q2_codes
gate_filtered_q2_lite_codes
deep_research_required_codes
```

必须满足：

```text
gate_processed_codes == expected_stage_b_codes
```

以及：

```text
expected_stage_b_codes
= gate_filtered_q1_codes
∪ gate_filtered_q2_codes
∪ gate_filtered_q2_lite_codes
∪ deep_research_required_codes
```

四集合必须互斥。

每个 Gate-filtered code 至少保留：

- `code`
- `gate_disposition`
- `gate_filter_reason`
- `gate_evidence`

Gate-filtered code **不得计入** `actual_deep_researched_codes`，也不得伪装成完整 Deep Research 四终态。

只有 Gate 全覆盖后，才允许定义：

```text
expected_deep_research_codes = deep_research_required_codes
```

### 8.3 Q2-lite 的外部资料边界

Q2-lite 是 Frozen Ledger Hard Gate 之后允许的极小定向公开研究，不属于 Stage A 信息边界污染。

每家公司最多 1–2 次定向公司查询，只允许取得 `SKILL.md 4.0` 定义的：

- 当期归母净利润；
- 扣非/经常性归母净利润；
- 公司披露的利润增长原因；
- 重大一次性/非经常性收益；
- 主导利润的联营/投资收益。

Q2-lite 不允许扩张为完整产业链、完整行业、催化剂、竞争格局或目标价研究。

如果 Q2-lite 无法形成明确 No：

```text
PASS_TO_FULL_DEEP_RESEARCH
```

不得为了降低研究数量追加搜索直到找到淘汰理由。

### 8.4 Deep Research 优先级只改变顺序

Gate 完成后，根据 `SKILL.md` 派生：

```text
deep_research_high_priority_codes
deep_research_low_priority_codes
```

要求：

```text
deep_research_required_codes
= high_priority_codes ∪ low_priority_codes
```

两集合互斥。

执行顺序：

1. HIGH_PRIORITY 先研究；
2. LOW_PRIORITY 后研究；
3. 每个优先级内部保持 frozen `deep_read_codes` 中的原始相对顺序；
4. LOW_PRIORITY 不是可跳过集合，本次 invocation 必须继续研究；
5. priority 不得写入公司最终状态，不得作为 waiting/excluded 理由。

### 8.5 Deep Research execution batch

为了在一次触发内完成全部 `expected_deep_research_codes`，采用批量优先、覆盖优先方式。

```text
batch_size = 12 companies
order = HIGH_PRIORITY original order → LOW_PRIORITY original order
```

最后一批可以少于 12 家。

执行要求：

1. 按上述确定性顺序构建 batch；
2. 同一工具调用中尽可能批量发起多个独立公司查询；
3. 公司自己的最新财报 / 业绩公告 / 交易所披露必须逐公司确认；
4. 同行业或同主导变量公共证据可以复用，但不得替代公司级依据；
5. runtime 已有确定性价格、估值、财务字段直接使用，不重复网页搜索；
6. 资料清楚的公司快速形成终态；只有业务异质、一次性收益、周期失真、来源冲突时追加更深检索；
7. 持续维护 `actual_deep_researched_codes`；
8. 必须继续直到 expected 全部形成终态，除非发生第 9.4 节定义的客观硬失败。

### 8.6 完整 Deep Research 公司级终态

只有一家公司在本次 invocation 完成足够公开资料核验并形成以下之一，才计入 actual：

- `confirmed`
- `waiting_for_entry`
- `research_uncertain`
- `excluded`

每家公司至少形成：

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

`waiting_for_entry_reason` 与 Uncertainty Resolution Pass 的审计要求以 `SKILL.md` 为准。

### 8.7 最低证据要求

完整 Deep Research 每家公司至少需要：

- 一项可核验的公司级主要公开依据，优先最新财报、业绩公告、交易所/公司正式披露；
- 对 `primary_profit_driver` / `dominant_risk_factor` 的证据支持；
- 至少一条能推翻当前判断的 `strongest_counterevidence`。

多个网站转载同一份公告只算同一个原始证据。

### 8.8 Stage B Diagnostic Probe｜只记录进度与真实故障

`research/last_execution_probe.json` 可记录但不用于续跑：

- `phase = STAGE_B_GATE / STAGE_B_DEEP_RESEARCH / PUBLICATION`
- `stage_b_expected_count`
- `gate_processed_count`
- `gate_filtered_q1_count`
- `gate_filtered_q2_count`
- `gate_filtered_q2_lite_count`
- `deep_research_required_count`
- `deep_research_high_priority_count`
- `deep_research_low_priority_count`
- `actual_deep_researched_count`
- `deep_research_batch_index`
- `deep_research_batch_count`
- `current_batch_codes`
- `last_completed_code`
- `tool_error`
- `hard_failure_reason`

**模型不得创建或选择 `STOPPED_EARLY` / `MODEL_TERMINATED_*` 作为控制流状态。**

在没有客观硬失败时：

- Gate coverage 未闭合 → 唯一合法下一动作是下一 Gate batch；
- Gate 已闭合但 Deep Research coverage 未闭合 → 唯一合法下一动作是下一 Deep Research batch；
- 不得为了写 probe、解释风险或生成用户回复而结束研究流程。

Probe 中只有在真实工具/系统/输入/一致性故障已经发生并且重试或协议允许的恢复路径失败后，才允许写 `hard_failure_reason`。该字段必须描述已经发生的具体错误，不能使用“预计耗时过长”“上下文过长”“候选过多”“可能做不完”“模型决定终止”等推测性理由。

---

## 9. Coverage｜正式榜双硬门

本轮维护：

```text
expected_stage_b_codes
gate_processed_codes
gate_filtered_q1_codes
gate_filtered_q2_codes
gate_filtered_q2_lite_codes
deep_research_required_codes
expected_deep_research_codes
actual_deep_researched_codes
```

### 9.1 Gate coverage

只有：

```text
gate_processed_codes == expected_stage_b_codes
```

并且 Gate 四集合互斥、并集等于 expected，才允许：

```text
gate_coverage = COMPLETE
```

### 9.2 Deep Research coverage

只有：

```text
expected_deep_research_codes == actual_deep_researched_codes
```

并且每个 expected code 都有唯一完整 Deep Research 四终态，才允许：

```text
deep_research_coverage = COMPLETE
```

如果 `expected_deep_research_codes` 为空，且 Gate coverage COMPLETE，则 Deep Research coverage 视为 COMPLETE，正式机会自然为空。

### 9.3 Stage B coverage

只有：

```text
gate_coverage == COMPLETE
AND deep_research_coverage == COMPLETE
```

才允许：

```text
stage_b_coverage = COMPLETE
```

随后才进入 Risk Cluster Consolidation 和正式榜。

### 9.4 FAILED / INCOMPLETE 只允许由客观硬失败触发

`FAILED / INCOMPLETE / UNVERIFIED` 不是 coverage 未闭合时可自主选择的退出状态。只有已经发生、可举证且无法按协议恢复的客观硬失败，导致本次 invocation 无法继续执行时，才允许失败收尾。

允许的客观硬失败包括：

- GitHub / Web / 其他必需工具明确返回错误，按规定重试后仍失败；
- 正式输入缺失、持续不可读或无法解析；
- Runtime Hard Gate 失败；
- Frozen Ledger Hard Gate 失败；
- Ledger / blob / run_id 发生并发覆盖或一致性冲突；
- Stage A 信息边界已经实际违规；
- 其他有明确系统/工具错误证据、使下一合法动作客观上无法执行的故障。

以下均**不是**客观硬失败：

- 候选数量大；
- 剩余 batch 多；
- 预计耗时长；
- 预计无法完成；
- 上下文已经很长；
- 已经找到足够多 confirmed；
- 市场风险高；
- 模型主观认为应当结束。

若客观硬失败发生时 coverage 尚未闭合，则：

```text
stage_b_coverage = INCOMPLETE
```

本次任务失败，不发布正式榜，并必须列出：

- `missing_gate_codes`
- `missing_deep_research_codes`
- `unexpected_researched_codes`（如有）
- `hard_failure_reason`
- 支持 `hard_failure_reason` 的实际工具/系统错误证据

INCOMPLETE 不产生可供下一次续跑的正式研究状态。下一次触发重新从 Stage A 开始。

不得把已完成子集包装成正式榜、临时榜、当前 Top N 或其他推荐名单。

### 9.5 UNVERIFIED

包括但不限于：

- Stage A 信息边界污染；
- Frozen Pre-Research Ledger 无效；
- expected_stage_b_codes 无法从本轮 frozen `deep_read_codes` 恢复；
- 当前正式输入与本轮 Ledger blob 不一致；
- Gate / Deep Research coverage 集合无法验证。

UNVERIFIED 同样只在对应客观验证失败实际发生时使用，不发布正式榜。

---

## 10. Risk Cluster Consolidation｜发布层去相关

前置条件：

```text
stage_b_coverage == COMPLETE
AND deep_research_coverage == COMPLETE
```

只有完整 Deep Research 得到的 `confirmed` 公司进入 Risk Cluster。

要求：

- 不改变 frozen `deep_read_codes`；
- 不改变 Gate-filtered 集合；
- 不改变 `deep_research_required_codes`；
- 不改变完整研究后的 confirmed / waiting_for_entry / research_uncertain / excluded；
- 正式榜排名对象是独立风险收益机会；
- 同一风险簇默认一个 `representative_code`；
- 同簇其他 confirmed 保留为 `alternative_codes`；
- 同行业存在多个独立机会时记录 `independence_rationale`；
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
- `stage_b_candidate_count`
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

### Stage B Gate

- `expected_stage_b_count`
- `gate_processed_count`
- `gate_coverage`
- `gate_filtered_q1_count`
- `gate_filtered_q2_count`
- `gate_filtered_q2_lite_count`
- `gate_filtered_q1_codes`
- `gate_filtered_q2_codes`
- `gate_filtered_q2_lite_codes`
- `deep_research_required_count`
- `deep_research_high_priority_count`
- `deep_research_low_priority_count`

### Deep Research

- `expected_deep_research_count`
- `actual_deep_researched_count`
- `deep_research_coverage`
- `stage_b_coverage`
- `company_confirmed_count`
- `waiting_for_entry_count`
- `research_uncertain_count`
- `excluded_count`
- `actual_deep_researched_codes`
- `missing_gate_codes`
- `missing_deep_research_codes`

### 程序漏斗

- `snapshot.trade_date`
- `universe_count`
- `source_candidate_count`
- Eligibility 各互斥排除原因数量
- `structural_relevance_count`
- `screening_group_count`

只有 `stage_b_coverage == COMPLETE` 时再发布：

- `risk_cluster_count`
- `formal_opportunity_count`
- `formal_representative_codes`
- `risk_cluster_map`
- `independence_rationale`

必须区分 `stage_b_candidate_count`、`deep_research_required_count`、`company_confirmed_count` 与 `formal_opportunity_count`。

---

## 12. 市场风险与执行覆盖

`bearish / weak breadth / high risk` 只能影响完整 Deep Research 后的估值、等待倾向与行动口径。

它不得：

- 改变程序候选全集；
- 跳过 Structured Screening；
- 修改 Stage A batch 边界；
- 修改 frozen `deep_read_codes`；
- 改写 Stage B Gate 的固定规则；
- 把 LOW_PRIORITY 当成可跳过；
- 成为 Gate 或 Deep Research coverage 不完整的理由；
- 在 Stage B coverage 未 COMPLETE 时生成正式榜。

---

## 13. 执行原则

> **每次任务触发都是一个全新、一步到位的完整事务；不得跨 invocation 续跑 Stage A、Gate 或公司研究。**

> **每次触发都从新的 Stage A 开始，上一轮 FROZEN Ledger 不得直接复用。**

> **screening_group_file 使用确定性的有界行区间完整消费。**

> **Stage A 按完整申万三级行业组原子化分批；batch 只降低执行负担。**

> **Stage A 只有 processed == candidate_count 时才允许一次性 FROZEN。**

> **Stage A 只做 repository-only Structured Screening；FROZEN 并回读验证之前不得使用公司级外部公开资料。**

> **Frozen Pre-Research Ledger 只是在同一次 invocation 内连接 Stage A 与 Stage B 的可审计硬检查点。**

> **Frozen Hard Gate 一旦 PASSED，唯一下一动作是 Gate Batch 1；在 Batch 1 实际开始前不存在模型自主失败收尾分支。**

> **不存在正式 Deep Research Ledger，不存在 resume_stage_b，不读取上一轮 company results。**

> **PEER_DOMINATED 只表达严格公司级支配，不承担行业/风险簇去重。**

> **`deep_read_codes` 是 Stage B 候选全集；Stage B Gate 必须完整覆盖后，才派生真正的 `deep_research_required_codes`。**

> **Gate 只做两问硬门和极小 Q2-lite；只有明确 No 才将该公司标记为 Gate-filtered，否则继续。**

> **Gate-filtered 不是完整 Deep Research 四终态。**

> **研究优先级只改变顺序，不改变 `deep_research_required_codes`；LOW_PRIORITY 仍必须同次完成。**

> **Stage B 完成的定义是 Gate coverage COMPLETE + Deep Research coverage COMPLETE，不是找到足够多可以出榜的公司。**

> **候选数量大、预计耗时长、预计研究不完，不是客观硬失败，也不是合法提前结束理由。**

> **模型不得创建 `STOPPED_EARLY` / `MODEL_TERMINATED_*` 作为自主控制流；失败收尾必须有已发生的客观硬失败证据。**

> **Stage B coverage 未 COMPLETE 时不得生成正式独立机会榜；若无客观硬失败则必须继续执行，若有客观硬失败才允许 INCOMPLETE 收尾。**

> **程序资格不由模型重算。**
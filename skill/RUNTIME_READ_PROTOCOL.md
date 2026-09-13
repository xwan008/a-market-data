# A股低风险买点榜｜运行时执行协议

本文件只定义：

- 如何锁定版本；
- Structured Screening 与 Deep Research 如何分成两个独立模型 run；
- 如何生成并验证持久化的 Frozen Ledger；
- 什么情况允许停止；
- Deep Research coverage 如何审计；
- coverage COMPLETE 后如何进入最终机会归并。

具体公司判断、Deep Research、估值、Risk Cluster Consolidation 与买点语义，以 `skill/SKILL.md` 为准。

---

## 1. 执行架构｜两个独立模型 Run

从本协议开始，模型执行不再在同一个 run 中同时承担 Structured Screening 和公司级公开资料研究。

正式执行分为两个独立模型任务：

```text
Run A｜Structured Screening Freeze
只使用 GitHub 锁定 runtime 中的结构化事实
→ 完成全部候选 Model Prescreen
→ 形成完整 Ledger
→ 持久化 research/pre_research_ledger.json
→ status = FROZEN

Run B｜Deep Research + Publication
只消费已经 FROZEN 的 Ledger
→ 不重新做 Pre-Research
→ 对 frozen deep_read_codes 做公司级公开资料研究
→ coverage audit
→ COMPLETE 后才允许 Risk Cluster + 正式机会榜
```

两个 run 的职责不能混合：

- Run A 不承担公司级公开资料 Deep Research，不生成正式榜；
- Run B 不重新做同行支配或公司绝对质量预筛，不修改 frozen `deep_read_codes`。

这样阶段边界由持久化交接物保证，而不是依赖同一次长执行中的自我约束。

---

## 2. 正式文件

仓库正式输入仍为：

- `skill/RUNTIME_READ_PROTOCOL.md`
- `skill/SKILL.md`
- `data/runtime/meta.json`
- `meta.screening_group_file`
- `meta.candidate_file`

新增模型阶段交接文件：

- `research/pre_research_ledger.json`

正式模型入口不包括：

- `peer_groups.json`
- `company_research_view.json`
- `data/runtime/details/`
- `data/runtime/screening_snapshot.json`
- `data/runtime/industry_state_compact.json`

`screening_group_file` 是 Structured Screening 的唯一模型工作视图；`candidate_file` 主要供 Deep Research 对 frozen 代码补充完整确定性背景。

---

## 3. Runtime Hard Gate

以下情况允许停止当前阶段：

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

具体结构阈值只读取 `meta.structural_rule`；协议和 Skill 不复制一套参数。

---

## 5. Run A｜Structured Screening Freeze

### 5.1 锁定源版本

Run A 开始时：

1. 获取 `xwan008/a-market-data` 当前 `main` commit SHA，记为 `source_runtime_commit_sha`；
2. 从该 SHA 读取 Protocol、Skill、`meta.json`、`screening_group_file`；
3. 记录这些正式文件的 Git blob SHA：
   - `protocol_blob_sha`
   - `skill_blob_sha`
   - `meta_blob_sha`
   - `screening_group_blob_sha`
   - `candidate_blob_sha`
4. Run A 的结构化判断只使用这一套冻结输入，不混入其他 runtime 版本。

### 5.2 Repository-only 信息边界

Run A 可以访问 GitHub，因为必须读取仓库正式 runtime。

但 Run A 的信息集只能来自锁定仓库中的结构化数据；在 Ledger FROZEN 前，禁止引入：

- 公司官网；
- 公司公告正文或交易所外部页面；
- 新闻；
- 券商研报；
- 搜索引擎结果；
- 行业网站或其他公司级外部公开资料。

因此本阶段准确语义是：

> **Repository-only Structured Screening，而不是“完全不能联网”。**

### 5.3 完成全部 Model Prescreen

按 `SKILL.md` 对全部 model-ready candidates 完成：

1. `PEER_DOMINATED`；
2. 对未被同行支配者判断：
   - `CLEARLY_WEAK`
   - `PASS_TO_DEEP_RESEARCH`
   - `UNCERTAIN`

单只组跳过同行支配判断，但不能跳过公司绝对质量判断。

每只结构候选最终恰好出现一次。

### 5.4 Frozen Ledger 集合约束

完整 Ledger 必须形成四个互斥集合：

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

只有满足完整集合闭合后，Ledger 才允许写成 `FROZEN`。

### 5.5 持久化交接物

Run A 唯一正式成功产物是：

```text
research/pre_research_ledger.json
```

该文件至少包含：

```json
{
  "ledger_version": 1,
  "status": "FROZEN",
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
  "peer_dominated_codes": [],
  "clearly_weak_codes": [],
  "pass_to_deep_research_codes": [],
  "uncertain_codes": [],
  "deep_read_codes": []
}
```

如果 109/109（或当轮实际 candidate_count）没有完整闭合，不得写 `status = FROZEN`。

Run A 不生成公司级公开资料结论、估值、Risk Cluster 或正式机会榜。

---

## 6. Run B｜Frozen Ledger 验证

Run B 开始时**先验证交接物，验证通过前不得做公司级公开资料查询**。

### 6.1 必须读取

从当前 `main` 读取：

- `research/pre_research_ledger.json`
- 当前 `skill/RUNTIME_READ_PROTOCOL.md`
- 当前 `skill/SKILL.md`
- 当前 `data/runtime/meta.json`
- 当前 `meta.screening_group_file`
- 当前 `meta.candidate_file`

### 6.2 Ledger Hard Gate

只有以下条件全部成立，Run B 才允许开始 Deep Research：

1. `ledger.status == "FROZEN"`；
2. `ledger.repository_only == true`；
3. `ledger.ledger_count == ledger.candidate_count`；
4. 四类代码集合互斥且并集等于当前 candidate 全集；
5. `deep_read_codes == pass_to_deep_research_codes ∪ uncertain_codes`；
6. 当前 `trade_date` 与 ledger `trade_date` 一致；
7. 当前候选数量与 ledger `candidate_count` 一致；
8. 当前以下 Git blob SHA 与 ledger 记录完全一致：
   - Protocol
   - Skill
   - meta
   - screening_groups
   - candidates

Git 主分支因为写入 Ledger 本身产生新的 commit SHA 是正常的；**是否仍是同一研究输入，以以上正式文件 blob SHA 是否一致判断，而不是要求 current main SHA 等于 `source_runtime_commit_sha`。**

任一条件失败：

```text
ledger_validation = FAILED
```

本轮停止，不得自行重新做 Pre-Research，也不得开始公司级公开资料研究；应等待 / 手动执行新的 Run A 生成与当前 runtime 匹配的 FROZEN Ledger。

### 6.3 Run B 不得修改预筛结果

验证通过后：

```text
expected_deep_research_codes = ledger.deep_read_codes
```

Run B 不得：

- 重新做 Peer Dominance；
- 把 `CLEARLY_WEAK` 或 `PEER_DOMINATED` 自行加回研究集合；
- 从 frozen `deep_read_codes` 中自行删除公司；
- 用实际搜索过的公司反推本应研究集合。

Frozen Ledger 是 Run A → Run B 的正式边界。

---

## 7. Run B｜Deep Research

Deep Research 唯一允许主动研究的公司集合是：

```text
ledger.deep_read_codes
```

不得：

- 重新自由挑选；
- 因为已经找到几只好公司就提前停止；
- 因为已经存在“足够出榜”的 confirmed 数量就提前停止；
- 因为预计正式榜已经足够丰富就跳过剩余公司；
- 因市场风险高而缩小冻结集合。

需要完整确定性背景时，从 `candidate_file` 中按 `deep_read_codes` 读取对应公司即可。

对每个 `deep_read_code` 最终形成足以进入：

- `confirmed`
- `waiting`
- `research_uncertain`
- `excluded`

之一的公司级研究状态。

Deep Research 同时应留下最终风险簇归并所需事实，包括 `primary_profit_driver` 与 `dominant_risk_factor`；具体判断语义由 `SKILL.md` 定义。

本阶段完成条件不是“找到若干可推荐公司”，而是 frozen 集合已经全部处理。

---

## 8. Deep Research coverage｜正式榜硬门

Run B 维护：

- `expected_deep_research_codes = ledger.deep_read_codes`
- `actual_deep_researched_codes`

只有完成足以形成公司级研究状态的公开资料核验，才计入 `actual_deep_researched_codes`；搜索请求次数不等于研究完成数。

### COMPLETE

```text
expected_deep_research_codes
==
actual_deep_researched_codes
```

只有 `COMPLETE` 才允许进入 Risk Cluster Consolidation 和正式独立机会榜生成。

### INCOMPLETE

集合不相等，必须列出：

- `missing_deep_research_codes`
- `unexpected_researched_codes`（如有）

此时不得生成正式独立机会榜，也不得把已完成研究的子集包装为临时正式榜、当前 Top N 或其他等价推荐结果。只允许输出覆盖审计、已完成公司状态和剩余未完成集合。

### UNVERIFIED

出现以下任一情况：

- Frozen Ledger 缺失；
- Ledger 不是 `FROZEN`；
- Ledger 集合无法闭合；
- Ledger 与当前正式 runtime / Skill / Protocol blob 不一致；
- 无法恢复 frozen `deep_read_codes`。

在新的两阶段架构下，**Run B 不再因为“自己在 Ledger 冻结前提前查询外部资料”进入 UNVERIFIED，因为 Run B 根本不负责冻结 Ledger；Ledger 验证通过之前，Run B 不开始 Deep Research。**

正式闭环唯一完成条件仍是：

```text
deep_research_coverage = COMPLETE
```

“已经找到足够多好公司”“已经够出榜”“已经达到某个推荐数量”都不是完成条件。

---

## 9. Final Opportunity Consolidation｜最终机会归并

前置条件：

```text
deep_research_coverage == COMPLETE
```

只有公司级 Deep Research 全部闭合、估值完成后，才进行最终风险簇归并。

具体如何判断同一 `risk_cluster`、如何选择代表公司、何时允许同一行业多个独立机会，由 `SKILL.md` 定义。

执行层要求：

1. 风险簇归并不得改变 `deep_read_codes`；
2. 风险簇归并不得修改 `actual_deep_researched_codes`；
3. 公司级 `confirmed / waiting / research_uncertain / excluded` 状态保持不变；
4. 正式榜排名对象是独立风险收益机会，同一风险簇默认一个 `representative_code`；
5. 同簇其他仍有价值的公司保留为 `alternative_codes`；
6. 若同一行业有多个正式席位，必须记录 `independence_rationale`；
7. 正式机会集合不设目标数量、不设固定上限、不做 Top N 截断；
8. 排名只表达优先级，不得作为停止研究或截断正式机会集合的理由。

风险簇归并是发布层去相关，不是研究层淘汰。

---

## 10. 最终审计漏斗

Run A 至少记录：

- `trade_date`
- `candidate_count`
- `ledger_count`
- `peer_dominated_count`
- `company_clearly_weak_count`
- `pass_to_deep_research_count`
- `uncertain_prescreen_count`
- `deep_research_candidate_count`
- 四类代码集合
- `deep_read_codes`
- 五个正式文件 blob SHA
- `ledger_status`

Run B 正式结果至少记录：

- `snapshot.trade_date`
- `universe_count`
- `source_candidate_count`
- Eligibility Filter 各互斥排除原因数量
- `structural_relevance_count`
- `screening_group_count`
- `ledger_validation`
- `deep_research_candidate_count`
- `actual_deep_researched_count`
- `deep_research_coverage`
- `company_confirmed_count`
- `research_uncertain_count`
- `waiting_count`
- `excluded_count`
- `deep_read_codes`
- `actual_researched_codes`

只有 `deep_research_coverage == COMPLETE` 时，才记录并发布：

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

前者是公司级研究结果数量；后者是去除共同主导风险因子后的正式独立机会数量。正式机会数量是完整研究后的自然结果，不是预先设定的任务目标。

---

## 11. 市场风险与执行覆盖

市场 `bearish / weak breadth / high risk` 只能影响最终估值、等待倾向，以及在 coverage COMPLETE 后自然形成的正式机会集合。

它不得：

- 改变程序候选全集；
- 跳过 Structured Screening；
- 修改 FROZEN Ledger；
- 改变 frozen `deep_read_codes`；
- 成为研究覆盖不完整的理由；
- 被用来绕过 Risk Cluster Consolidation；
- 被用来在 coverage 未 COMPLETE 时生成正式榜。

---

## 12. 执行原则

> **程序先完成确定性筛选；Run A 只做 repository-only Structured Screening 并冻结 Ledger；Run B 才做公司级公开资料研究。**

> **Frozen Ledger 是两个模型 run 之间的正式交接物，不再依赖同一次长执行里的阶段自律。**

> **Run B 不重新做 Pre-Research，也不得修改 frozen deep_read_codes。**

> **任务完成的定义是穷尽 frozen deep_read_codes，不是找到足够多可以出榜的公司。**

> **Deep Research coverage 未 COMPLETE 时，没有正式独立机会榜。**

> **正式机会集合没有目标数量和固定上限；排名只表示优先级。**

> **程序资格不由模型重算。**

> **研究覆盖完整性和最终榜风险去重是两件不同的事。**
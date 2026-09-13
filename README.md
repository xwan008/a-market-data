# A-Market-Data

A 股低风险买点榜的数据、程序筛选与研究规则仓库。

## 核心原则

> **程序负责事实和资格，模型负责关系和解释。**

> **研究层防漏，发布层去相关。**

> **每次任务触发必须一步到位；不跨 invocation 续跑 Stage A 或公司研究。**

系统不要求模型从全市场自由挑股票，也不把可公式化的工作交给模型。每次 07:00、19:00 或手动触发都视为一个全新的完整事务：本轮从 Stage A 开始，完成本轮 Frozen Ledger，然后在同一次 invocation 内把全部 frozen `deep_read_codes` 研究到 coverage COMPLETE，最后才允许 Risk Cluster Consolidation 与正式榜。

---

## 当前执行流程

```text
全市场行情 / 财务 / 估值 / K线 / 行业数据
        ↓
Eligibility Filter｜程序
        ↓
source candidates
        ↓
Structure Filter｜程序
        ↓
model-ready candidates
        ↓
生成正式 runtime：
meta.json / candidates.json / screening_groups.json
        ↓
Runtime / Identity Gate
        ↓
screening_groups 按固定 40 行区间完整读取
        ↓
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Stage A｜Structured Screening
repository-only
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
完整申万三级行业组不可拆分
按原顺序做同一 invocation 内 execution batch
目标约 20 家/批
        ↓
全部 candidate 100% 覆盖
        ↓
research/pre_research_ledger.json
BUILDING → 一次性 FROZEN
        ↓
重新读取 Ledger + 五个正式文件
        ↓
Frozen Ledger Hard Gate
        ↓
FAILED → 本轮停止
PASSED
        ↓
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Stage B｜Deep Research
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
按 frozen deep_read_codes 既定顺序
固定 12 家/批
        ↓
confirmed / waiting_for_entry /
research_uncertain / excluded
        ↓
expected == actual ?
        ↓
NO → 本轮 INCOMPLETE / FAILED，不出榜
YES → coverage COMPLETE
        ↓
正常化估值 + 最终安全区
        ↓
Risk Cluster Consolidation
只处理 confirmed / entry_ready
        ↓
一个 risk cluster = 一个 formal opportunity
representative + alternatives
        ↓
正式独立风险收益机会集合
```

### 不存在跨轮续跑

当前正式架构明确不存在：

```text
Stage A partial checkpoint
Deep Research Ledger
resume_stage_b
parent_run_id
跨 invocation remaining 恢复
上一轮 company_results 自动复用
```

上一轮 Stage A 或 Deep Research 只完成一部分，只代表上一轮失败；下一次任务仍然生成新的 run_id，并从新的 Stage A 开始。

---

## Program Filter

### Eligibility Filter

`scripts/build_snapshot.py` 是 Eligibility Filter 的正式实现，负责行业资格、ST、价格、利润、估值、严重收入/利润恶化、财务与趋势数据可用性等确定性筛选。

### Structure Filter

`scripts/split_snapshot.py` 是 Structure Filter 的唯一计算真相源，输出：

- `structure_tier`
- `strong_support`
- `strong_volume_zone`
- `meta.structural_rule`

下游不得重新硬编码另一套结构阈值。

所有公司与行业 YoY 在正式 runtime 中统一使用 `percentage_points`。

---

## 正式 runtime

正式 runtime 只保留：

```text
data/runtime/meta.json
data/runtime/candidates.json
data/runtime/screening_groups.json
```

### `meta.json`

记录交易日、Eligibility audit、source / structural candidate 数、结构规则、runtime validation、screening group validation 与正式文件位置。

### `candidates.json`

保存通过 Structure Filter 的完整确定性背景，供 Stage B 按本轮 frozen codes 使用。

### `screening_groups.json`

Stage A 的唯一模型工作视图。采用自描述列式、行可寻址 JSON。正式消费路径按 `line_count` 直接使用固定 40 行区间读取，不依赖一次整文件响应是否完整。

它只组织结构化事实，不预先产生模型结论，不评分、不排名、不做 Top N。

---

## Stage A｜Structured Screening

每次触发创建新的 `run_id`，先把：

```text
research/pre_research_ledger.json
```

写为本轮 `BUILDING`。

Stage A 只能使用锁定 GitHub runtime 的结构化事实。在本轮 Ledger FROZEN 并重新读取通过 Hard Gate 前，禁止引入公司官网、公告正文、新闻、研报、搜索引擎结果或行业网站等公司级外部资料。

### Execution batch

Stage A 为降低一次性模型负担采用 execution batch，但最小不可拆分单位是一个完整申万三级行业组：

```text
target_batch_candidate_count = 20
```

按 `screening_groups` 原始顺序确定性打包。同一三级行业组绝不拆分；批次不具有排名、配额、Top N 或淘汰名额意义。

部分 batch 的判断只存在于当次 invocation 内存中，不能写成 FROZEN checkpoint，也不能供下一轮恢复。只有全部 candidate 都得到唯一 `ledger_entry` 后，才允许一次性 FROZEN。

### 四类结果

- `PEER_DOMINATED`
- `CLEARLY_WEAK`
- `PASS_TO_DEEP_RESEARCH`
- `UNCERTAIN`

`PEER_DOMINATED` 只表示同一三级行业组内结构化事实已经足以支持严格公司级支配，不承担行业去重、风险簇去重或减少 Deep Research 数量的职责。

`CLEARLY_WEAK` 只有在结构化事实显示多个独立方面明显偏弱，且没有清晰的确定性反向优势时才使用。单一指标不得单独形成 `CLEARLY_WEAK`；如果弱点仍可能由周期、会计口径、业务变化或缺失信息解释，应使用 `UNCERTAIN`。

最终：

```text
deep_read_codes
=
PASS_TO_DEEP_RESEARCH ∪ UNCERTAIN
```

完整字段与 Hard Gate 以 `skill/RUNTIME_READ_PROTOCOL.md` 为唯一执行契约。

---

## Stage B｜单次执行 Deep Research

Stage B 只研究本轮 Frozen Ledger 的 `deep_read_codes`。

正式 execution batch 固定为：

```text
batch_size = 12 companies
order = frozen deep_read_codes 的既定顺序
```

行业、真实主营和共享主导变量只用于选择分析框架与复用公共证据，不得重新排序或重组 execution batch。

禁止读取上一轮公司研究结果跳过本轮研究；禁止把历史 actual / remaining 计入当轮 coverage。

每家公司本轮正式状态只允许：

- `confirmed`
- `waiting_for_entry`
- `research_uncertain`
- `excluded`

其中：

```text
confirmed
= research_supported + entry_ready

waiting_for_entry
= research_supported + not_entry_ready
```

因此：

```text
research_supported_count
= confirmed_count + waiting_for_entry_count

entry_ready_count
= confirmed_count
```

`waiting` 只作为历史结果的 legacy alias；新运行统一输出 `waiting_for_entry`。

每家公司需要确认真实主营、`primary_profit_driver`、`dominant_risk_factor`、未来 1–2 季度盈利逻辑、盈利质量/一次性收益/周期正常化、最强反向证据与估值摘要。

### 一步到位执行方式

Deep Research 采用**批量优先、覆盖优先**：

- 同一工具调用尽量批量组织多个公司查询；
- 公司自身最新财报、业绩公告或正式披露逐公司确认；
- 共享行业驱动证据可一次获取后映射到相关公司；
- runtime 已有的价格、估值、财务事实不重复去网页搜索；
- 资料清楚的公司快速形成终态；业务异质、一次性收益、周期失真或来源冲突时再追加必要检索；
- 不得因为已经完成任意中间数量或已经找到若干 confirmed 而结束。

Batch 只决定一起处理谁，不决定留下谁；同一 Batch 可以有多个、全部或零个 confirmed。

---

## Deep Research coverage

本轮：

```text
expected_deep_research_codes = frozen deep_read_codes
```

只有本次 invocation 真正形成公司级终态的 code 才计入：

```text
actual_deep_researched_codes
```

正式发布硬门：

```text
expected_deep_research_codes
==
actual_deep_researched_codes
```

只有 `COMPLETE` 才允许 Risk Cluster 与正式榜。

如果本轮结束时仍有 missing codes：

```text
deep_research_coverage = INCOMPLETE
```

本轮任务失败，不发布临时 Top N，也不保存为下次续跑入口。

---

## Risk Cluster 与最终机会榜

Risk Cluster Consolidation 只在 coverage COMPLETE 后执行，并且只处理 `confirmed / entry_ready_codes`。

它根据完整 Deep Research 已确认的：

- `primary_profit_driver`
- 主要上涨催化
- `dominant_risk_factor`
- 主要反向风险

判断多个公司是否实质表达同一风险收益机会，而不是按申万行业机械归并。

因此：

```text
研究对象 = 公司
正式榜对象 = 独立风险收益机会
```

同一风险簇的所有 entry-ready 公司仍保持 `confirmed`；正式榜只选择一个 `representative_code`，其他 confirmed 作为 `alternative_codes` 保留。

发布层硬不变量：

```text
formal_opportunity_count
== risk_cluster_count
== len(formal_representative_codes)
```

```text
confirmed_codes
= formal_representative_codes ∪ all_alternative_codes
```

并要求 representatives 与 alternatives 互斥、每个 confirmed 恰好属于一个 risk cluster、每个 cluster 恰好一个 representative。

不再使用 `final_recommendation_count`，正式榜数量只使用 `formal_opportunity_count` 表达。

正式机会集合不设目标数量、不设固定上限、不做 Top N 截断。

---

## `research/` 目录职责

当前 `research/` 正式存在两个文件：

```text
research/pre_research_ledger.json
research/last_execution_probe.json
```

### `pre_research_ledger.json`

唯一正式阶段检查点，只承担**同一次 invocation 内** Stage A → Stage B 的硬边界。下一轮会以新 run_id 覆盖为新的 BUILDING，不是跨轮缓存。

### `last_execution_probe.json`

仅为运行诊断遥测：

```text
diagnostic_only = true
formal_input = false
reuse_for_research = false
```

它可以记录 Stage A / Stage B 的 batch、processed、错误与终止位置，但不得保存为下一轮研究恢复入口，也不得参与投资判断。

当前正式运行不保存、读取或恢复 Stage B 的跨轮公司研究 checkpoint。

---

## 规则文件职责

```text
README.md
= 给人看的架构说明

skill/RUNTIME_READ_PROTOCOL.md
= 唯一执行契约：读取、批次、阶段、覆盖、Hard Gate、发布验证

skill/SKILL.md
= 唯一模型判断规则：Stage A 判断、Deep Research 状态、估值、Risk Cluster 语义

Automation
= 当前仍保留与仓库规则一致的执行细节；待连续多轮稳定后再做第 7 项精简
```

若 README 与正式规则冲突，以 Protocol / Skill 为准。

---

## Workflows

### 每日更新

`.github/workflows/update-data.yml`

负责日行情、价格结构、市场状态、行业状态、snapshot 与统一 runtime build。

### 每周研究更新

`.github/workflows/update-weekly-research.yml`

负责完整财务 / 估值复核、行业状态、snapshot 与统一 runtime build。

### 独立重建

`.github/workflows/rebuild-runtime.yml`

从仓库现有数据重建 runtime。

Pre-Research Ledger 与 execution probe 的写入不属于这些 workflow 的市场数据重建入口。

---

## 最终原则

```text
能用公式100%确定的 → 程序
关系与结构化解释 → Stage A 模型
需要新增公开事实的 → Stage B Deep Research
共同风险去重 → coverage COMPLETE 后的 Risk Cluster
```

以及最重要的执行约束：

> **一次触发，一次完整结果；做不完就是本轮失败，不跨轮续存。**

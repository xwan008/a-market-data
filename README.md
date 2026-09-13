# A-Market-Data

A 股低风险买点榜的数据、程序筛选与研究规则仓库。

## 核心原则

> **程序负责事实和资格，模型负责关系和解释。**

> **研究层防漏，发布层去相关。**

> **每次任务触发必须一步到位；不跨 invocation 续跑公司研究。**

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
screening_groups｜程序组织
        ↓
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Stage A｜Structured Screening
repository-only
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
本轮新 run_id
        ↓
research/pre_research_ledger.json
BUILDING → FROZEN
        ↓
重新读取 Ledger + 正式文件
        ↓
Frozen Ledger Hard Gate
        ↓
FAILED → 本轮停止
PASSED
        ↓
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Stage B｜Deep Research
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
本次 invocation 内穷尽 frozen deep_read_codes
        ↓
confirmed / waiting /
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
        ↓
正式独立风险收益机会集合
```

### 不存在跨轮续跑

当前正式架构明确不存在：

```text
Deep Research Ledger
resume_stage_b
parent_run_id
跨 invocation remaining 恢复
上一轮 company_results 自动复用
```

上一轮研究到 40/91，不代表下一轮从 41 开始。它只代表上一轮失败；下一次任务仍然从新的 Stage A 开始，并重新完成当轮全部 Deep Research。

`research/pre_research_ledger.json` 只承担**同一次 invocation 内** Stage A → Stage B 的硬边界，不是跨轮缓存。

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

Stage A 的唯一模型工作视图。当前采用自描述列式、行可寻址 JSON，以减少重复字段名和模型输入成本，同时支持按行区间完整读取。

它只组织结构化事实，不预先产生模型结论，不评分、不排名、不做 Top N。

---

## Stage A｜Structured Screening

每次触发都必须创建新的 `run_id`，并先把：

```text
research/pre_research_ledger.json
```

写为本轮 `BUILDING`。

Stage A 只能使用锁定 GitHub runtime 的结构化事实。在本轮 Ledger FROZEN 并重新读取通过 Hard Gate 前，禁止引入公司官网、公告正文、新闻、研报、搜索引擎结果或行业网站等公司级外部资料。

Stage A 对全部结构候选形成四类结果：

- `PEER_DOMINATED`
- `CLEARLY_WEAK`
- `PASS_TO_DEEP_RESEARCH`
- `UNCERTAIN`

并形成覆盖全部候选的逐公司 `ledger_entries`。

`PEER_DOMINATED` 只表示结构化事实已经足以支持严格公司级支配，不允许承担行业去重、风险簇去重或减少 Deep Research 数量的职责。

最终：

```text
deep_read_codes
=
PASS_TO_DEEP_RESEARCH ∪ UNCERTAIN
```

完整字段与 Hard Gate 以 `skill/RUNTIME_READ_PROTOCOL.md` 为唯一契约。

---

## Stage B｜单次执行 Deep Research

Stage B 只研究本轮 Frozen Ledger 的 `deep_read_codes`。

禁止读取上一轮公司研究结果来跳过本轮研究；禁止把历史 actual / remaining 计入当轮 coverage。

每家公司在本轮必须形成以下之一：

- `confirmed`
- `waiting`
- `research_uncertain`
- `excluded`

并确认真实主营、`primary_profit_driver`、`dominant_risk_factor`、未来 1–2 季度盈利逻辑、盈利质量/一次性收益/周期正常化、最强反向证据与估值摘要。

### 一步到位执行方式

为了让单次定时任务完成全部 frozen 集合，Deep Research 采用**批量优先、覆盖优先**：

- 同一工具调用尽量批量组织多个公司查询；
- 公司自身最新财报、业绩公告或正式披露逐公司确认；
- 共享行业驱动证据可一次获取后映射到相关公司；
- runtime 已有的价格、估值、财务事实不重复去网页搜索；
- 资料清楚的公司快速形成终态；业务异质、一次性收益、周期失真或来源冲突时再追加深检索；
- 不得因为已经完成 10、20、40 家或已经找到若干 confirmed 而结束。

最低证据要求不是“机械搜很多网站”，而是：公司级主要公开依据 + 对盈利驱动/主导风险的支持 + 最强反向证据。多个网站转载同一份公告仍只算同一个原始证据。

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

Risk Cluster Consolidation 只在 coverage COMPLETE 后执行。

它根据完整 Deep Research 已确认的：

- `primary_profit_driver`
- 主要上涨催化
- `dominant_risk_factor`
- 主要反向风险

判断多个公司是否实质表达同一风险收益机会。

因此：

```text
研究对象 = 公司
正式榜对象 = 独立风险收益机会
```

同一风险簇默认一个 `representative_code`，其他仍有价值公司作为 `alternative_codes` 保留。

组内代表优先级：

> **最终安全边际 → 保守上行空间 → 基本面稳定性 → 参与时机**

正式机会集合不设目标数量、不设固定上限、不做 Top N 截断。

---

## `research/` 目录职责

当前正式运行只允许：

```text
research/pre_research_ledger.json
```

作为同一次 invocation 内的 Stage A 检查点。

当前正式运行不保存、读取或恢复 Stage B 的跨轮公司研究 checkpoint。历史 Deep Research 结果如未来需要保留，只能作为明确的 archive / 人工复盘资料，不能进入当前模型执行入口。

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

Pre-Research Ledger 写入不属于这些 workflow 的 push trigger 路径，因此不会意外触发市场数据重建。

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

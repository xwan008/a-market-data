# A-Market-Data

A 股低风险买点榜的数据、程序筛选与研究规则仓库。

## 核心原则

> **程序负责事实和资格，模型负责关系和解释。**

> **研究层防漏，发布层去相关。**

> **main 只维护当前最终契约，不维护 v1 / v2 / v3 并行兼容层。**

系统不要求模型从全市场自由挑股票。确定性规则先由程序完成，模型 Structured Screening 只处理无法安全公式化的关系判断；公司级外部资料只能在 Frozen Pre-Research Ledger 通过 Hard Gate 后进入 Deep Research。

当前正式流程：

1. **Program Filter**：Eligibility + Structure，全部为确定性程序规则；
2. **Structured Screening**：模型只使用锁定 GitHub runtime 的结构化事实，完成严格同行支配与公司绝对质量判断；
3. **Frozen Pre-Research Ledger**：完整逐公司审计、冻结 `deep_read_codes`；
4. **Frozen Ledger Hard Gate**：回读验证信息边界、集合闭合与五个正式输入 blob SHA；
5. **Deep Research Ledger**：持久化 expected / actual / remaining 与公司级终态研究结果；
6. **Deep Research**：只研究 frozen `deep_read_codes`，可跨多次 invocation 从 remaining 断点续跑；
7. **Risk Cluster Consolidation**：只有 Deep Research coverage COMPLETE 后，才按真实盈利驱动与主导风险因子做发布层去相关。

系统仍然只有一个正式“A股低风险买点榜”任务。断点续跑是同一任务内部的 Stage B 执行机制，不新增第二个 Automation。

---

## 当前执行流程

```text
全市场数据
        ↓
Eligibility Filter｜程序
        ↓
Structure Filter｜程序
        ↓
model-ready candidates
        ↓
data/runtime/screening_groups.json
        ↓
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Stage A｜Structured Screening
repository-only
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        ↓
research/pre_research_ledger.json
BUILDING → FROZEN
        ↓
Frozen Ledger Hard Gate
        ↓
PASSED
        ↓
research/deep_research_ledger.json
status = BUILDING
expected = frozen deep_read_codes
actual / remaining 可持久化
        ↓
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Stage B｜Deep Research
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
从 remaining 继续
每完成最多10家终态结果就 checkpoint
同一 invocation 有能力则继续下一批
        ↓
INCOMPLETE
→ 保存 actual / remaining
→ 不发布正式榜
→ 下一次在 parent/runtime/blob 全一致时直接续 Stage B

COMPLETE
expected == actual
remaining = ∅
        ↓
正常化估值 + 最终安全区
        ↓
Risk Cluster Consolidation
        ↓
正式独立风险收益机会集合
```

真正的阶段边界不是时间间隔：

```text
完整 Structured Screening
→ FROZEN Pre-Research Ledger
→ 回读 Hard Gate
→ 才允许公司级外部 Deep Research
```

真正的 Stage B 完成边界是：

```text
expected_deep_research_codes
==
actual_deep_researched_codes
```

而不是“已经找到足够多好公司”。

---

## Program Filter

### Eligibility Filter

`scripts/build_snapshot.py` 是 Eligibility Filter 的正式实现，负责行业资格、ST、价格规则、正利润、估值上限、严重收入/利润同步恶化，以及财务、趋势和价格结构数据可用性。

`data/snapshot.json -> eligibility_audit` 使用互斥第一失败原因闭合全市场漏斗：

```text
全市场
=
industry_ineligible
+ st
+ price_rule
+ non_positive_profit
+ valuation_ceiling
+ severe_revenue_profit_deterioration
+ data_or_trend_incomplete
+ eligible
```

### Structure Filter

`scripts/split_snapshot.py` 是 Structure Filter 的唯一计算真相源，正式输出：

- `structure_tier`
- `strong_support`
- `strong_volume_zone`
- `meta.structural_rule`

下游不得复制另一套结构阈值。

---

## 正式 runtime

正式 runtime 只保留：

```text
data/runtime/meta.json
data/runtime/candidates.json
data/runtime/screening_groups.json
```

### `meta.json`

记录交易日、程序漏斗、结构规则、候选数量、screening group coverage / validation，以及正式文件位置。

### `candidates.json`

保存通过 Structure Filter 的完整确定性字段。Stage B 对 frozen 公司需要补充完整结构化背景时按 code 读取。

### `screening_groups.json`

Stage A 唯一正式模型工作视图。当前格式是**列式、行可寻址 JSON**：

- `member_columns` 定义 member row 字段位置；
- 每家公司用一行数组表达，避免重复 JSON key；
- `meta.screening_group_serialization.line_count` 提供完整行数；
- `line_addressable=true` 时允许按有界行区间完整消费。

它包含：

- 价格结构事实；
- PE / PB / ROE；
- 收入 / 利润 / 扣非 / 现金流 / 毛利率；
- 行业状态与行业 YoY；
- 程序可确定的质量标签。

程序不在这里预先计算模型结论，不评分、不排名、不做 Top N。

YoY 单位统一为：

```text
percentage_points
```

即 `12.4` 表示 `12.4%`。

---

## Structured Screening 边界

Stage A 可以访问 GitHub，但信息集只能来自锁定 runtime。

FROZEN + Hard Gate PASSED 前禁止引入：

```text
公司官网 / 公告正文 / 新闻 / 券商研报 /
搜索引擎结果 / 行业网站 / 其他公司级外部公开资料
```

准确表述：

```text
Structured Screening = repository-only
Deep Research = repository context + public external evidence
```

### PEER_DOMINATED 不是去相关工具

`PEER_DOMINATED` 只允许表达严格公司级 Pareto 支配。

不能因为：

- 同行业候选太多；
- 最终可能属于同一 risk cluster；
- 希望减少 Deep Research 数量；
- 最终榜只需要一个行业席位；
- 想“只留最好1–2只”；

而提前淘汰。

相关性去重只能发生在完整 Deep Research 后的 Risk Cluster Consolidation。

---

## Pre-Research Ledger｜Stage A 硬检查点

正式文件：

```text
research/pre_research_ledger.json
```

每个新的 Stage A 先写：

```text
status = BUILDING
run_id = 本轮唯一值
```

全部候选逐公司审计闭合、信息边界 CLEAN、集合校验通过后才允许：

```text
status = FROZEN
```

至少记录：

- `run_id`
- `source_runtime_commit_sha`
- Protocol / Skill / meta / screening_groups / candidates 五个 Git blob SHA
- `trade_date`
- `candidate_count / ledger_count`
- 四类代码集合
- `deep_read_codes`
- 覆盖全部候选的 `ledger_entries`

代码集合必须能由 `ledger_entries[].result` 完整重建。

Ledger 写入会产生新 Git commit，因此研究输入一致性使用正式文件 blob SHA，不要求 main commit SHA 保持不变。

---

## Deep Research Ledger｜Stage B 可恢复检查点

正式文件：

```text
research/deep_research_ledger.json
```

它严格绑定一个 FROZEN Pre-Research Ledger：

```text
parent_run_id
parent_pre_research_blob_sha
trade_date
Protocol / Skill / meta / screening / candidates blob SHA
expected_deep_research_codes
```

同时持久化：

```text
actual_deep_researched_codes
remaining_deep_research_codes
company_results
checkpoint_count
```

每个 `company_result` 只有在足以形成以下终态之一后才能写入：

```text
confirmed
waiting
research_uncertain
excluded
```

并至少保存真实主营、盈利驱动、主导风险因子、未来盈利逻辑、盈利质量/正常化判断、最强反向证据、估值摘要与稳定公开资料来源。

### 断点恢复

下一次任务触发时，如果：

- Frozen Pre-Research Ledger 仍通过 Hard Gate；
- parent_run_id 一致；
- parent Pre-Research Ledger blob 一致；
- trade_date 一致；
- 五个正式输入 blob 一致；
- expected 与 frozen deep_read_codes 一致；
- actual / remaining / company_results 闭合；

则：

```text
resume_stage_b = true
```

直接从 remaining 继续，不重新执行 Stage A，不重复研究 actual。

任何正式输入、父 Ledger 或 expected 集合变化都会使旧 Deep Research checkpoint 失效。

### Checkpoint 批次

每完成最多 10 家新的公司终态结果就持久化一次；如果同一 invocation 仍有执行能力，继续下一批。

因此：

> **批次只是持久化粒度，不是研究上限，不是 Top N，也不是推荐数量。**

---

## Deep Research coverage

必须始终满足：

```text
expected = actual ∪ remaining
actual ∩ remaining = ∅
company_results[].code = actual
```

正式发布硬门：

```text
deep_research_coverage == COMPLETE
```

等价于：

```text
expected == actual
remaining = ∅
company_results_count == expected_count
```

如果 `INCOMPLETE`：

- 保存 checkpoint；
- 报告 actual / remaining；
- 下一次满足恢复条件时从 remaining 继续；
- 不生成正式榜；
- 不允许把已研究子集包装成临时 Top N。

如果 `UNVERIFIED`：不得发布，也不得复用旧 checkpoint。

---

## Risk Cluster 与最终机会榜

只有 Deep Research coverage COMPLETE 后才能执行。

Risk Cluster 根据 Deep Research 已确认的：

- `primary_profit_driver`
- 主要上涨催化
- `dominant_risk_factor`
- 最重要反向风险

判断多个公司是否实际上表达同一个风险收益机会。

因此：

```text
研究对象 = 公司
正式榜对象 = 独立风险收益机会
```

同一风险簇默认一个 `representative_code`，其余有价值公司作为 `alternative_codes` 保留。

组内代表沿用既有优先级：

> **最终安全边际 → 保守上行空间 → 基本面稳定性 → 参与时机**

正式机会集合：

```text
不设目标数量
不设固定上限
不做 Top N 截断
```

---

## `research/` 目录职责

当前 active checkpoint 只允许：

```text
research/pre_research_ledger.json
research/deep_research_ledger.json
```

历史 Deep Research 结果、旧榜单或其他临时研究产物不是当前正式输入。

Git 历史负责保留旧审计；当前 main 文件只表达当前有效/待构建状态。

---

## 单一 runtime 构建入口

所有数据 workflow 统一调用：

```bash
python scripts/build_runtime.py data/snapshot.json --output-dir data/runtime
```

`build_runtime.py` 内部负责 Structure Filter、screening groups 生成、candidate/screening exact match、结构规则、YoY 单位和正式 runtime 校验。

---

## Workflows

### 每日更新

`.github/workflows/update-data.yml`

负责日行情、价格结构、市场状态、行业状态、snapshot 和统一 runtime build。

### 每周研究更新

`.github/workflows/update-weekly-research.yml`

负责完整财务 / 估值复核、行业状态、snapshot 和统一 runtime build。

### 独立重建

`.github/workflows/rebuild-runtime.yml`

从仓库现有数据重建 compact snapshot，再调用统一 runtime builder。

两个 Ledger 的写入不属于上述数据 workflow 的正常触发路径。

---

## 文件职责

| 文件 | 唯一职责 |
| --- | --- |
| `scripts/build_snapshot.py` | Eligibility Filter + 全市场审计 |
| `scripts/split_snapshot.py` | Structure Filter 唯一计算源 |
| `scripts/build_screening_groups.py` | 组织 Stage A 列式、行可寻址结构化工作视图 |
| `scripts/build_runtime.py` | 统一构建与验证正式 runtime |
| `skill/SKILL.md` | Model Prescreen、Deep Research、估值、Risk Cluster 判断语义 |
| `skill/RUNTIME_READ_PROTOCOL.md` | 执行顺序、输入锁定、两个 Ledger、断点恢复、coverage 与发布硬门 |
| `research/pre_research_ledger.json` | Stage A 可审计冻结集合 |
| `research/deep_research_ledger.json` | Stage B 可恢复公司级研究进度 |
| `data/runtime/meta.json` | 正式 runtime 元数据与校验状态 |
| `data/runtime/candidates.json` | Structure 后完整确定性候选事实 |
| `data/runtime/screening_groups.json` | Stage A 唯一模型工作视图 |

---

## 最终不变量

```text
能公式化的 → 程序
需要关系判断的 → Structured Screening
必须新增外部事实的 → Deep Research
Stage B 容量不足 → 持久化 checkpoint，不降低覆盖标准
完整研究后 → Risk Cluster 发布层去相关
```

> **任务完成的定义是穷尽 frozen deep_read_codes，而不是找到足够多可以出榜的公司。**

# A-Market-Data

A 股低风险买点榜的数据、程序筛选与研究规则仓库。

## 核心原则

> **程序负责事实和资格，模型负责关系和解释。**

> **研究层防漏，发布层去相关。**

系统不把可公式化的工作交给模型，也不要求模型从全市场自由挑股票。Deep Research 之前属于结构化筛选阶段，内部由程序硬筛和模型 Structured Screening 分工；只有 Frozen Ledger 硬检查点通过后才允许引入公司级外部公开资料。

当前逻辑：

1. **Program Filter**：Eligibility + Structure，全部为确定性程序规则；
2. **Structured Screening Freeze**：模型只使用锁定 GitHub runtime 的结构化事实，判断严格同行支配和公司绝对质量；
3. **Frozen Ledger Hard Gate**：持久化后重新读取 Ledger，验证逐公司审计、集合闭合、信息边界、run_id 和正式文件 blob SHA；
4. **Deep Research**：只消费通过 Hard Gate 的 `deep_read_codes`，引入公开资料形成真实业务判断、正常化估值与最终安全区；
5. **Risk Cluster Consolidation**：只有 Deep Research coverage 完整闭合后，才按主导盈利驱动和风险因子做发布层去相关。

这些步骤由**一次任务触发严格串行执行**，不拆成不同时间点。

任务完成条件不是“找到足够多可以出榜的公司”，而是 frozen `deep_read_codes` 全部得到公司级研究结论。

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
Ledger 先置 BUILDING + run_id
        ↓
Peer Dominance
+ Company Prescreen
        ↓
全部候选逐公司 entry 闭合
        ↓
research/pre_research_ledger.json
status = FROZEN
        ↓
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Frozen Ledger Hard Gate
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
重新读取 Ledger + 正式文件
验证：
- run_id / schema / status
- 109/109 entries（以当轮实际数量为准）
- 四集合与 entries 严格一致
- PEER_DOMINATED 具备 dominated_by + 多维依据
- repository-only 信息边界未污染
- Protocol / Skill / meta / screening / candidates blob 一致
        ↓
FAILED → 整轮停止
PASSED → Stage B
        ↓
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Stage B｜Deep Research
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
穷尽 frozen deep_read_codes
        ↓
confirmed / waiting /
research_uncertain / excluded
        ↓
Deep Research coverage audit
        ↓
INCOMPLETE / UNVERIFIED
→ 只输出审计，不生成正式榜

COMPLETE
        ↓
正常化估值 + 最终安全区
        ↓
Risk Cluster Consolidation
        ↓
正式独立风险收益机会集合
```

真正的阶段边界不是“等一小时”，而是：

```text
完整 Structured Screening
→ FROZEN Ledger 持久化
→ 重新读取并通过 Hard Gate
→ 才允许公司级外部 Deep Research
```

如果在 Ledger FROZEN 前已经引入公司级外部资料，本轮信息边界被污染，不能靠后来补齐 Ledger 恢复可验证性。

---

## 程序筛选

### Eligibility Filter

`scripts/build_snapshot.py` 是 Eligibility Filter 的正式实现。

它负责：

- 行业资格；
- ST；
- 价格规则；
- 正利润；
- 估值上限；
- 严重收入 / 利润同步恶化；
- 财务、趋势和价格结构数据可用性。

`data/snapshot.json` 中的 `eligibility_audit` 使用**互斥第一失败原因**记录全市场漏斗：

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

本审计只解释现有固定规则，不修改策略阈值。

### Structure Filter

`scripts/split_snapshot.py` 是 Structure Filter 的唯一计算真相源。

它计算并输出：

- `structure_tier`
- `strong_support`
- `strong_volume_zone`
- `meta.structural_rule`

下游不得重新硬编码一套结构阈值。具体参数以当期 `data/runtime/meta.json -> structural_rule` 为准。

---

## YoY 单位

公司和行业 YoY 在正式 snapshot / runtime 中统一使用：

```text
percentage_points
```

即：

```text
12.4 = 12.4%
```

生成和验证链路都会检查单位一致性。

---

## 正式 runtime

正式 runtime 目录只保留：

```text
data/runtime/meta.json
data/runtime/candidates.json
data/runtime/screening_groups.json
```

### `meta.json`

记录交易日、Eligibility audit、source / structural candidate 数、`structural_rule`、Structure audit、runtime 文件位置、screening group coverage 与 validation 状态。

### `candidates.json`

保存通过 Structure Filter 的完整确定性字段。Stage B 对 frozen 幸存者需要完整背景时按代码读取。

### `screening_groups.json`

Structured Screening 的唯一模型工作视图，按申万三级行业组织：

- 价格结构事实；
- 正式 `structure_tier`；
- PE / PB / ROE；
- 收入 / 利润 / 扣非 / 现金流 / 毛利率；
- 行业状态和行业 YoY；
- 程序可 100% 计算的质量标签。

程序不在该文件中预先计算模型结论，不评分、不排名、不做 Top N。

旧的 `peer_groups.json`、`company_research_view.json` 等不再是正式入口。

---

## Structured Screening 的边界

Structured Screening 可以访问 GitHub，但信息集只能来自锁定 runtime。

不得提前引入：

```text
公司官网 / 公告正文 / 新闻 / 券商研报 /
搜索引擎结果 / 行业网站等公司级外部公开资料
```

准确表述：

```text
Structured Screening = repository-only
Deep Research = repository context + public external evidence
```

### PEER_DOMINATED 不是去相关工具

`PEER_DOMINATED` 只允许在同组 B 对 A 形成严格公司级 Pareto 支配、且不存在需要公开研究才能确认的差异化优势时使用。

以下都不能作为 PEER_DOMINATED 理由：

- 同行业候选太多；
- 多家公司可能共享同一风险因子；
- 最终榜只希望一个行业席位；
- 为了减少 Deep Research 数量；
- “只留最好的 1–2 只”。

这些问题只允许在 Deep Research coverage COMPLETE 后由 Risk Cluster Consolidation 处理。

---

## Frozen Ledger｜同一次执行内部的硬检查点

正式检查点：

```text
research/pre_research_ledger.json
```

当前 Ledger 字段契约由 `skill/RUNTIME_READ_PROTOCOL.md` 直接定义，不维护历史 schema 分支或兼容层。

每轮开始先写：

```text
status = BUILDING
run_id = 本轮唯一值
```

使旧 FROZEN Ledger 立即失效，并防止重叠执行互相覆盖。

只有全部结构候选完成 Model Prescreen、Stage A 信息边界 CLEAN，并且逐公司审计闭合后才允许：

```text
status = FROZEN
```

Ledger 至少记录：

- `run_id`
- `source_runtime_commit_sha`
- Protocol / Skill / meta / screening_groups / candidates 的 Git blob SHA；
- `trade_date`
- `candidate_count`
- `ledger_count`
- `repository_only = true`
- `external_company_research_before_freeze = false`
- 四类代码集合；
- `deep_read_codes`
- `ledger_entries`：覆盖全部候选的逐公司审计。

每个 entry 至少包含：

```text
code
result
reason_code
reason
```

`PEER_DOMINATED` entry 额外必须有：

```text
dominated_by
price_structure_basis
valuation_basis
operating_basis
differentiated_advantage_check
uncertainty_check
```

代码集合是 entries 的派生索引，必须能由 entries 完整重建且严格一致。

Ledger FROZEN 后必须重新读取，不能直接依赖模型内存进入 Stage B。

写入 Ledger 会产生新的 Git commit，因此同一研究输入使用正式文件 **blob SHA** 校验，而不是要求 current main SHA 与 `source_runtime_commit_sha` 相同。

---

## Deep Research coverage

Stage B 只研究：

```text
expected_deep_research_codes
= ledger.deep_read_codes
```

并维护：

```text
actual_deep_researched_codes
```

只有足以形成公司级 `confirmed / waiting / research_uncertain / excluded` 状态的公开资料核验完成后才计入 actual。

正式发布硬门：

```text
deep_research_coverage == COMPLETE
```

即 expected 与 actual 集合完全一致。

如果 `INCOMPLETE` 或 `UNVERIFIED`：

```text
只输出覆盖审计
+ 已完成公司状态
+ missing / unexpected codes
```

不生成正式独立机会榜，也不允许把已研究子集包装成临时 Top N。

---

## Risk Cluster 与最终机会榜

Risk Cluster Consolidation 只在 Deep Research coverage COMPLETE 后执行。

它不是“同行业只留一只”，而是根据 Deep Research 已确认的：

- `primary_profit_driver`
- 主要上涨催化
- `dominant_risk_factor`
- 最重要的反向风险

判断多个公司是否实际上表达同一个风险收益机会。

因此：

```text
研究对象 = 公司
正式榜对象 = 独立风险收益机会
```

同一风险簇默认一个 `representative_code`，其余有价值公司作为 `alternative_codes` 保留。

组内代表沿用既有优先级，不新增综合评分：

> **最终安全边际 → 保守上行空间 → 基本面稳定性 → 参与时机**

正式机会集合：

```text
不设目标数量
不设固定上限
不做 Top N 截断
```

数量由完整研究自然产生。

---

## `research/` 目录职责

当前正式运行只允许把：

```text
research/pre_research_ledger.json
```

作为阶段检查点读取。

历史 Deep Research 结果、旧榜单或其他研究产物不属于本轮正式输入；不得因为文件名日期相同就复用为本轮事实。

如果未来需要长期保存研究结果，应建立明确的 archive / manifest 契约并绑定 source ledger blob/run_id；在此之前不把临时研究结果文件留在正式 `research/` 入口旁边。

---

## 单一 runtime 构建入口

所有数据 workflow 统一调用：

```bash
python scripts/build_runtime.py data/snapshot.json --output-dir data/runtime
```

`build_runtime.py` 内部负责：

1. Structure Filter；
2. 生成 `screening_groups.json`；
3. 校验 candidate / screening 股票全集一致；
4. 校验结构规则状态；
5. 校验 YoY 单位；
6. 确认旧 runtime 视图不存在。

---

## Workflows

### 每日更新

`.github/workflows/update-data.yml`

负责日行情、价格结构、市场状态、行业状态、snapshot，以及统一 runtime build。

### 每周研究更新

`.github/workflows/update-weekly-research.yml`

负责完整财务 / 估值复核、行业状态、snapshot，以及统一 runtime build。

### 独立重建

`.github/workflows/rebuild-runtime.yml`

从仓库现有数据重建 compact snapshot，再调用统一 runtime builder。

Ledger 文件更新不属于上述 workflow 的 push trigger 路径，因此不会因为 Stage A 写入 BUILDING/FROZEN 而意外触发市场数据重建。

---

## 文件职责

| 文件 | 唯一职责 |
| --- | --- |
| `scripts/build_snapshot.py` | Eligibility Filter + 全市场审计 |
| `scripts/split_snapshot.py` | Structure Filter 唯一计算源 |
| `scripts/build_screening_groups.py` | 组织 repository-only 结构化筛选事实 |
| `scripts/build_runtime.py` | 统一 runtime 构建与验证 |
| `research/pre_research_ledger.json` | Stage A → Stage B 的 Frozen Ledger v3 硬检查点 |
| `skill/SKILL.md` | Structured Screening、Deep Research、Risk Cluster 的判断语义 |
| `skill/RUNTIME_READ_PROTOCOL.md` | 单次串行执行、版本/Blob、Ledger schema、coverage 与正式榜硬门 |
| `README.md` | 给人看的稳定架构说明 |

---

## 不变原则

> **市场风险影响最终行动，不影响既定研究覆盖。**

> **程序结构硬筛只是研究准入，不是最终价值底。**

> **Structured Screening 只使用锁定 GitHub runtime；Deep Research 才引入公司级外部公开资料。**

> **一次任务触发严格执行 Stage A → FROZEN Ledger Hard Gate → Stage B。**

> **PEER_DOMINATED 只做真正公司级明确支配，不做行业/风险簇去重。**

> **研究层防漏，发布层去相关。**

> **任务完成看 frozen deep_read_codes 是否全部研究完，不看已经找到了多少只好公司。**

> **Deep Research coverage 未 COMPLETE 时，不生成正式独立机会榜。**

> **正式机会集合不设目标数量、固定上限或 Top N 截断。**

> **不为了压缩数量而引入综合评分、Top N 或不可审计的模型自由挑选。**
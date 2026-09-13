# A-Market-Data

A 股低风险买点榜的数据、程序筛选与研究规则仓库。

## 核心原则

> **程序负责事实和资格，模型负责关系和解释。**

系统不把可公式化的工作交给模型，也不要求模型从全市场自由挑股票。Deep Research 之前属于同一个大阶段——结构化筛选，但内部按职责分为程序硬筛和模型结构化预筛；公司级外部公开资料研究在 Frozen Ledger 硬检查点通过之后才开始。

当前逻辑分为：

1. **Program Filter**：Eligibility + Structure，全部为确定性程序规则；
2. **Structured Screening Freeze**：模型只使用锁定 GitHub runtime 的结构化事实，判断同行支配和公司绝对质量，生成完整 Frozen Ledger；
3. **Frozen Ledger Hard Gate**：持久化后重新读取 Ledger，验证集合闭合、信息边界和正式文件 blob SHA；
4. **Deep Research**：只消费通过 Hard Gate 的 `deep_read_codes`，引入公司级公开资料，形成真实业务判断、正常化估值与最终安全区；
5. **Risk Cluster Consolidation**：只有 Deep Research coverage 完整闭合后，才把高度依赖同一主导风险因子的公司归为一个独立风险收益机会。

这些步骤由**一次任务触发严格串行执行**，不再为了阶段隔离拆成不同时间点。

研究层保持完整覆盖，最终发布层再做风险因子去重。

**任务完成条件不是“找到足够多可以出榜的公司”，而是 frozen `deep_read_codes` 全部得到公司级研究结论。**

---

## 当前执行流程

```text
全市场行情 / 财务 / 估值 / K线 / 行业数据
        ↓
1. Eligibility Filter｜程序
   行业资格 + 公司基础风险资格
        ↓
source candidates
        ↓
2. Structure Filter｜程序
   位置 + 支撑 + 成交密集区承接质量
        ↓
model-ready candidates
        ↓
3. screening_groups｜程序组织
   同行业一次性准备价格结构 / 估值 / 经营 / 行业事实
        ↓
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Stage A｜Structured Screening Freeze
只使用锁定 GitHub runtime
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Ledger 先置 BUILDING
        ↓
   Peer Dominance
   + Company Prescreen
        ↓
   全部候选闭合
        ↓
research/pre_research_ledger.json
status = FROZEN
        ↓
冻结 deep_read_codes
        ↓
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Frozen Ledger Hard Gate
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   重新读取 Ledger
   + 验证四集合闭合
   + 验证 repository_only
   + 验证 FROZEN 前未发生公司级外部研究
   + 验证 runtime / Skill / Protocol blob 一致
        ↓
   FAILED → 整轮停止
   PASSED → 才进入 Stage B
        ↓
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Stage B｜Deep Research + Publication
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   对 frozen deep_read_codes 做公司级公开资料研究
        ↓
   必须穷尽 frozen deep_read_codes
        ↓
4. Deep Research coverage audit
        ↓
   ├─ INCOMPLETE / UNVERIFIED
   │    → 只输出覆盖审计与剩余集合
   │    → 不生成正式独立机会榜
   │
   └─ COMPLETE
        ↓
5. 正常化估值 + 最终安全区
        ↓
6. Risk Cluster Consolidation
   按主导盈利驱动与风险因子去重
        ↓
正式独立机会集合
├─ representative_code
└─ alternative_codes

公司级状态仍保留：
confirmed / waiting / research_uncertain / excluded
```

Stage A 和 Stage B 属于同一次任务执行中的两个严格串行阶段。Stage A 不承担公司级公开资料查询和榜单生成；Stage B 不重新做 Peer Dominance / Company Prescreen，也不能修改 frozen `deep_read_codes`。

真正的边界不是“等一小时”或“另一个任务”，而是：

```text
完整 Structured Screening
→ FROZEN Ledger 持久化
→ 重新读取并通过 Hard Gate
→ 才允许公司级外部 Deep Research
```

如果在 Ledger FROZEN 前已经引入公司级外部公开资料，本轮信息边界被污染，不能靠后来补齐 Ledger 恢复可验证性。

不使用综合加权总分、全市场 Top N、“找到足够多就停止”或“市场风险高所以只研究少数公司”的方式替代完整研究。

正式机会集合不设目标数量和固定上限；数量由完整研究结果自然产生。

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

`data/snapshot.json` 中的 `eligibility_audit` 使用**互斥第一失败原因**记录全市场漏斗，因此可以解释：

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

`scripts/split_snapshot.py` 是 Structure Filter 的**唯一计算真相源**。

它计算并输出：

- `structure_tier`
- `strong_support`
- `strong_volume_zone`
- `meta.structural_rule`

下游文件不得重新硬编码一套结构阈值。

具体阈值以当期 `data/runtime/meta.json -> structural_rule` 为准；README、Skill 和 Protocol 不复制易漂移的参数。

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

不再允许行业聚合使用 `0.124`、公司字段使用 `12.4` 的混合表示。

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

记录：

- 交易日和 snapshot 元数据；
- Eligibility audit；
- source / structural candidate 数；
- `structural_rule`；
- Structure Filter audit；
- runtime 文件位置；
- screening group 数量和 coverage；
- validation 状态。

### `candidates.json`

保存通过 Structure Filter 的完整确定性字段。

Structured Screening 不需要扫描整张表；Deep Research 对冻结幸存者需要更完整背景时按代码读取。

### `screening_groups.json`

唯一的 Structured Screening 模型工作视图。

按申万三级行业分组，每家公司一次性提供：

- 价格结构事实；
- 正式 `structure_tier`；
- PE / PB / ROE；
- 收入 / 利润 / 扣非 / 现金流 / 毛利率；
- 行业状态和行业 YoY；
- 程序可 100% 计算的财务质量标签。

程序不在该文件中预先计算模型结论，不评分、不排名、不做 Top N。

旧的：

- `peer_groups.json`
- `company_research_view.json`

已经由 `screening_groups.json` 取代。

---

## Frozen Ledger｜同一次执行内部的硬检查点

正式检查点文件：

```text
research/pre_research_ledger.json
```

它不是市场数据源，而是模型 Structured Screening 的持久化结果。

每轮 Structured Screening 开始前先将其写为：

```text
status = BUILDING
```

使上一轮 Frozen Ledger 立即失效。

只有全部结构候选完成 Model Prescreen、四类集合完整闭合且 Stage A 没有引入公司级外部公开资料后，才允许：

```text
status = FROZEN
```

至少记录：

- `source_runtime_commit_sha`
- Protocol / Skill / meta / screening_groups / candidates 的 Git blob SHA；
- `trade_date`
- `candidate_count`
- `ledger_count`
- `repository_only = true`
- `external_company_research_before_freeze = false`
- `peer_dominated_codes`
- `clearly_weak_codes`
- `pass_to_deep_research_codes`
- `uncertain_codes`
- `deep_read_codes`

其中：

```text
deep_read_codes
=
pass_to_deep_research_codes
∪ uncertain_codes
```

Ledger 写成 FROZEN 后必须重新读取，不能直接依赖模型内存进入 Deep Research。

Hard Gate 会验证 Ledger 与当前正式 runtime、Skill、Protocol 的 blob SHA 完全一致。写入 Ledger 自己会产生新的 Git commit，因此不要求 current main commit SHA 与 `source_runtime_commit_sha` 相同；判断同一输入版本看正式文件 blob 是否一致。

如果 Ledger 缺失、未 FROZEN、集合不闭合、Stage A 信息边界被污染或 blob 不一致，整轮停止，不允许开始公司级 Deep Research。

---

## Structured Screening 与 Deep Research 的信息边界

Structured Screening 可以访问 GitHub，但只能使用锁定 runtime 的结构化事实。

它不得引入：

```text
公司官网 / 公告正文 / 新闻 / 券商研报 / 搜索引擎结果 / 行业网站等公司级外部公开资料
```

所以准确表述是：

```text
Structured Screening = repository-only
Deep Research = repository context + public external evidence
```

而不是简单的“联网 / 不联网”。

核心研究边界：

```text
Stage A 完整 Structured Screening
→ 持久化 FROZEN Ledger
→ 重新读取 Ledger
→ Hard Gate 验证通过
→ Stage B 才允许公司级公开资料 Deep Research
```

如果 Stage A 在 FROZEN 前提前使用公司级外部资料：

```text
stage_a_information_boundary = VIOLATED
→ Ledger 不得可信 FROZEN
→ Deep Research coverage = UNVERIFIED
→ 整轮停止
```

Deep Research coverage 以：

```text
expected_deep_research_codes
vs
actual_deep_researched_codes
```

做集合审计，而不是按搜索请求次数推断。

正式发布硬门是：

```text
deep_research_coverage == COMPLETE
```

如果 coverage 为 `INCOMPLETE` 或 `UNVERIFIED`：

```text
只输出覆盖审计
+ 已完成公司状态
+ missing_deep_research_codes
```

不生成正式独立机会榜，也不允许把已研究子集包装成临时 Top N。

只有 coverage COMPLETE 后，才进入 Risk Cluster Consolidation。

---

## Risk Cluster 与最终机会榜

Risk Cluster 不是“同行业只留一只”，而是判断多个公司是否实际上依赖同一个核心盈利变量、上涨催化和下行风险。

因此：

```text
研究对象 = 公司
正式榜对象 = 独立风险收益机会
```

同一风险簇默认只有一个 `representative_code` 占正式榜席位，其余有价值公司作为 `alternative_codes` 保留。

同一行业如果 Deep Research 证明主营、利润来源和主导风险实质不同，可以分别形成独立机会；不同行业如果高度依赖同一个主导变量，也可以归入同一风险簇。

Risk Cluster Consolidation 只改变最终榜表达，不得反向减少 `deep_read_codes` 或修改 Deep Research coverage。

正式机会集合：

```text
不设目标数量
不设固定上限
不做 Top N 截断
```

如果完整研究后只有 3 个独立机会，就输出 3 个；如果有 14 个都满足条件，就输出 14 个；如果没有，则正式机会集合为空。

排名只用于表达机会优先级，不作为任务完成条件或截断条件。

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

这样日更、周更和独立重建不会分别维护不同的 runtime 生成命令。

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

从仓库现有数据重建 compact snapshot，再调用统一 runtime builder。它适用于规则或 runtime 结构修改后的验证，不依赖重新抓取外部市场数据。

---

## 文件职责

| 文件 | 唯一职责 |
| --- | --- |
| `scripts/build_snapshot.py` | Eligibility Filter + 全市场审计 |
| `scripts/split_snapshot.py` | Structure Filter 唯一计算源 |
| `scripts/build_screening_groups.py` | 组织 repository-only 结构化筛选事实 |
| `scripts/build_runtime.py` | 统一 runtime 构建与验证 |
| `research/pre_research_ledger.json` | 同一次执行内 Stage A → Stage B 的 Frozen Ledger 硬检查点 |
| `skill/SKILL.md` | 模型判断语义，包括 Structured Screening、Deep Research 和 Risk Cluster Consolidation |
| `skill/RUNTIME_READ_PROTOCOL.md` | 单次串行两阶段、版本/Blob 锁定、Frozen Ledger、coverage、正式榜硬门与最终机会审计 |
| `README.md` | 给人看的稳定架构说明 |

---

## 不变原则

> **市场风险影响最终行动，不影响既定研究覆盖。**

> **程序结构硬筛只是研究准入，不是最终价值底。**

> **Structured Screening 只使用锁定 GitHub runtime；Deep Research 才引入公司级外部公开资料。**

> **一次任务触发严格执行 Stage A → FROZEN Ledger Hard Gate → Stage B。**

> **Frozen Ledger 是同一次执行内部的硬检查点，不是两个任务之间的时间交接。**

> **单公司研究失败只影响该公司，不阻断其他候选。**

> **研究层宁可完整保留相关公司，行动层再按主导风险因子去重。**

> **任务完成看 frozen deep_read_codes 是否全部研究完，不看已经找到了多少只好公司。**

> **Deep Research coverage 未 COMPLETE 时，不生成正式独立机会榜。**

> **正式榜排名的是独立风险收益机会，不是简单的股票数量。**

> **正式机会集合不设目标数量、固定上限或 Top N 截断。**

> **不为了压缩数量而引入综合评分、Top N 或不可审计的模型自由挑选。**

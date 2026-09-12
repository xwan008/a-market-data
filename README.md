# A-Market-Data

A 股低风险买点榜的数据、程序筛选与研究规则仓库。

## 核心原则

> **程序负责事实和资格，模型负责关系和解释。**

系统不把可公式化的工作交给模型，也不要求模型从全市场自由挑股票。程序先完成数据准备、Eligibility Filter、Structure Filter 和统一 screening view；模型只在两个阶段介入：

1. **Pre-Research Screening**：不联网，判断同行支配和公司绝对质量；
2. **Deep Research**：只研究冻结后的 `deep_read_codes`，形成真实业务判断、正常化估值与最终安全区。

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
4. Pre-Research Screening｜模型，不联网
   先同行支配，再公司绝对质量
        ↓
完整 Ledger
        ↓
冻结 deep_read_codes
        ↓
5. Deep Research｜模型，联网
   主营 / 盈利驱动 / 周期 / 盈利质量 / 反向证据
        ↓
6. 正常化估值 + 最终安全区
        ↓
正式榜 / waiting / research_uncertain / excluded
```

不使用综合加权总分、全市场 Top N 或“市场风险高所以只研究少数公司”的方式替代完整研究。

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

模型不需要在 Pre-Research 阶段扫描整张表；它主要在 Deep Research 对冻结幸存者需要更完整背景时按代码读取。

### `screening_groups.json`

唯一的 Pre-Research Screening 工作视图。

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

## Pre-Research 与 Deep Research

模型判断语义只维护在：

```text
skill/SKILL.md
```

执行顺序、版本锁定、Ledger 冻结和 coverage 审计只维护在：

```text
skill/RUNTIME_READ_PROTOCOL.md
```

核心执行边界：

```text
完整 Pre-Research
→ 冻结 Ledger
→ deep_read_codes
→ 才允许公司级 Web Research
```

Deep Research coverage 以：

```text
expected_deep_research_codes
vs
actual_deep_researched_codes
```

做集合审计，而不是按搜索请求次数推断。

---

## 单一 runtime 构建入口

所有 workflow 统一调用：

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
| `scripts/build_screening_groups.py` | 组织不联网预筛事实 |
| `scripts/build_runtime.py` | 统一 runtime 构建与验证 |
| `skill/SKILL.md` | 模型判断语义 |
| `skill/RUNTIME_READ_PROTOCOL.md` | 版本锁定、阶段顺序、Ledger 与 coverage |
| `README.md` | 给人看的稳定架构说明 |

---

## 不变原则

> **市场风险影响最终行动，不影响既定研究覆盖。**

> **程序结构硬筛只是研究准入，不是最终价值底。**

> **单公司研究失败只影响该公司，不阻断其他候选。**

> **不为了压缩数量而引入综合评分、Top N 或不可审计的模型自由挑选。**

# A-Market-Data

A 股低风险买点榜的数据、程序筛选与研究规则仓库。

## 核心架构

当前架构遵循一条原则：

> **确定性计算交给程序，解释与研究判断交给模型。**

模型不再读取数百个单股 runtime 文件，也不再逐只计算结构硬规则。

正式模型输入只有：

- `data/runtime/meta.json`
- `data/runtime/candidates.json`
- `skill/RUNTIME_READ_PROTOCOL.md`
- `skill/SKILL.md`

底层行情、K 线、财务、行业状态、snapshot 等继续作为程序生成源存在，但不是模型正式研究入口。

---

## 数据与研究流程

```text
全市场行情 / 财务 / 估值 / K线 / 行业数据
        ↓
程序机械风险粗筛
        ↓
snapshot 机械候选全集
        ↓
程序计算结构硬规则
support distance / volume-zone distance / 60日位置
        ↓
model-ready candidates.json
        ↓
模型按申万三级行业三维比较
价格结构 / 估值质量 / 经营质量
        ↓
未被同行明确支配的候选
        ↓
公开资料 Deep Research
        ↓
正常化估值 + 最终安全区
        ↓
正式榜 / waiting / research_uncertain / excluded
```

---

## 程序结构硬筛

当前潜在结构相关性使用三个确定性信号：

1. 当前价距 `support_center` <= 5%；
2. 当前价距 `volume_zone_center` <= 5%；
3. `position_pct <= 35%`。

原则上至少满足两项才进入 `data/runtime/candidates.json`。

这一步只回答：

> **当前价格是否值得投入进一步研究资源。**

它不是最终安全区判断。

最终 `low_risk_buy_range` 只能由模型在公司 Deep Research 后，将正常化估值、PE/PB/ROE/增长/现金流与支撑、前低、成交密集区等共同验证后形成。

---

## model-ready 候选表

`data/runtime/candidates.json` 是模型唯一的结构化候选输入。

每行已经合并：

- 股票代码、名称、申万三级行业；
- 行业盈利状态与市场确认字段；
- PE-TTM、动态 PE、PB、ROE、市值；
- 营收、利润、扣非、现金流、毛利率；
- 20/60 日价格位置、MA、趋势；
- 支撑区 low/high/center/touches；
- 成交密集区 low/high/center/volume share；
- 阻力区与 invalidation；
- 已计算好的结构距离与信号数。

行按 `industry_code + code` 排序，便于模型直接做同行横向比较。

不再生成：

- `data/runtime/details/`
- `data/runtime/screening_snapshot.json`
- `data/runtime/industry_state_compact.json`

---

## 模型三维比较

模型不做综合总分。

在同一申万三级行业内固定比较：

1. **价格结构**：当前价离潜在承接区域有多近、结构风险是否可控；
2. **估值质量**：PE/PB 是否得到 ROE、增长和盈利质量支持；
3. **经营质量**：收入、利润、扣非、现金流等是否真实改善。

只有某家公司在三个维度都不明显优于同行、且至少一个维度明显更差，并且不存在业务异质性或周期失真需要进一步研究时，才允许在公开 Deep Research 前被同行明确支配而排除。

不使用全市场综合排名、Top N 或“市场风险高所以只研究少数公司”的截断方式。

---

## Runtime 文件

```text
data/runtime/meta.json        # 版本、交易日、市场状态、候选数、validation
data/runtime/candidates.json  # 唯一 model-ready 候选表
```

`meta.json` 记录至少包括：

- `runtime_format = model_ready_candidates_v1`
- `source_candidate_count`
- `candidate_count`
- `structural_relevance_count`
- `candidate_file`
- `candidate_columns`
- `structural_rule`
- `runtime_validation`

---

## 数据更新

### 每日更新

`.github/workflows/update-data.yml` 负责：

- 行情与估值更新；
- K 线和价格结构更新；
- market state；
- 行业状态；
- snapshot；
- model-ready runtime。

### 每周研究数据更新

`.github/workflows/update-weekly-research.yml` 负责：

- 全市场财务与估值复核；
- 行业映射；
- 行业盈利状态；
- snapshot；
- model-ready runtime。

### 独立 runtime 重建

`.github/workflows/rebuild-runtime.yml` 可以直接从现有 `data/snapshot.json` 重建 runtime，并验证唯一候选表的格式与关键字段。

---

## 研究规则

- `skill/RUNTIME_READ_PROTOCOL.md`：版本锁定、数据可信边界、Hard Gate 和唯一候选表读取协议；
- `skill/SKILL.md`：同行比较、公司研究、正常化估值、安全边际、上下行空间和最终排名规则。

研究层始终遵守：

> **市场风险影响最终行动，不影响候选研究覆盖。**

> **程序结构硬筛只是研究准入，不是最终价值底。**

> **局部公司研究失败只影响该公司，不阻断整轮任务。**

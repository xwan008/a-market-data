# A股低风险买点榜｜运行时执行协议

本文件是唯一正式执行契约。

## 0. 唯一改动边界

相对原低风险流程，**只改行业入口这一处**：

```text
原流程：全部盈利/可研究行业 → 对应股票 → Stage A → Stage B Gate → Deep Research → 正式榜

当前流程：全部盈利/可研究行业
→ 直接读取 industry_state.json
→ 从中选最近景气更好、资金正在集中进入的 3 个行业
→ 只取这 3 个行业对应股票
→ Stage A → Stage B Gate → Deep Research → 正式榜
```

除“先缩成 3 个行业”外，Stage A、Frozen Ledger、Stage B Gate、Deep Research、Unified Entry Evaluation、Risk Cluster、价格纪律与发布语义全部沿用原流程，不得因为行业入口变化而新增 lifecycle / activation / 额外行业 Gate。

---

## 1. 正式输入

每次 19:00 收盘正式版或手动正式触发，读取当前 `main`：

- `skill/RUNTIME_READ_PROTOCOL.md`
- `skill/SKILL.md`
- `data/runtime/meta.json`
- `meta.screening_group_file`
- `meta.candidate_file`
- `data/research/industry_state.json`

每次触发都是新的独立事务，不复用上一轮 Stage A / Gate / Deep Research 结论。

---

## 2. Bootstrap / Runtime Hard Gate

必须确认：

- `runtime_validation.status == passed`；
- snapshot 为当前最近有效正式收盘；
- meta / screening_groups / candidates 可解析；
- candidate 与 screening group 股票全集一致；
- candidate code 唯一；
- `screening_group_validation.status == passed`；
- `screening_group_validation.line_addressable == true`；
- YoY 单位为 `percentage_points`；
- runtime 使用正式旧版结构筛选字段：`structure_tier / strong_support / strong_volume_zone`；
- `industry_state.json` 可解析、`status == valid`、trade date 与正式收盘一致。

只有这些客观 Hard Gate 失败才允许整轮 FAILED。

候选少、行业少、Stage A / Stage B 尚未完成，都不是 FAILED 理由；没有客观硬失败时必须继续执行。

---

## 3. Stage 0｜industry_state 直接选 3 个行业

### 3.1 不做全行业公开研究

Stage 0 **只读取 `data/research/industry_state.json`**。

禁止把 Stage 0 扩张成：

- 对 333 个行业逐一做公开研究；
- 为证明“严格全市场前三”而额外联网；
- 从热点新闻或个股反推行业；
- 新建 T0/T1/T2 深研任务；
- 在这一层研究公司。

`industry_state.json` 已经提供行业盈利/景气与市场资金结构的确定性聚合底稿，Stage 0 的职责只是从中缩小搜索空间。

### 3.2 先沿用原来的盈利行业资格

行业基础资格沿用原流程，不新增条件：

```text
trend == improving
OR
(trend == stable AND breadth in {broad, divergent})
```

这一步只是得到“原来本来就会继续下钻”的盈利/可研究行业池。

### 3.3 再从该池中选最近景气 + 资金最集中的 3 个

选择只使用 `industry_state.json` 已有字段，不联网：

**景气/盈利侧：**

- `trend`
- `strength`
- `breadth`
- `confidence`
- `core_improving_breadth`
- `aggregate_revenue_yoy`
- `aggregate_parent_profit_yoy`

**资金/市场侧：**

- `market_confirmation`
- `market_activity`
- `market_breadth`
- `market_metrics.breadth_score`
- `market_metrics.median_volume_ratio_vs_20d`
- `market_metrics.expanding_volume_share`
- `market_metrics.day_up_ratio`
- `market_metrics.strong_up_ratio`
- `market_metrics.five_day_up_ratio`

选择原则：

1. 先保证行业仍属于原盈利/可研究池；
2. 优先景气 `improving`、盈利改善广度更高、收入/利润趋势更好的行业；
3. 在这些行业中优先 `market_confirmation=strong`、`market_activity=active`、上涨广度高、成交扩散明显、相对量能增强的方向；
4. 目标是找“最近景气仍在 + 资金正在集中”的 3 个行业，不要求证明数学意义上的绝对 Top 3；
5. 若满足条件不足 3 个，按实际数量；不得用明显弱行业凑数。

产出：

```text
selected_industry_codes
selected_industry_names
```

固定以后，**Stage 0 立即结束**。

### 3.4 行业层到此为止

从这一刻起：

- 不得再用行业景气标签删个股；
- 不得再用行业资金标签删个股；
- 不得引入 lifecycle / activation tier；
- 不得因为某只股票“没有跟上行业当日上涨”就直接排除；
- 个股是否值得研究，完全回到原 Stage A / Stage B / Deep Research 规则。

---

## 4. screening_group 消费规则

`screening_group_file` 是 Stage A 正式工作视图。

按 `meta.screening_group_serialization.line_count` 使用 40 行有界区间完整读取；不得依赖一次整文件返回。

完整读取后，只保留 `industry_code in selected_industry_codes` 的完整申万三级组作为本轮 Stage A universe。

一个行业组不可拆分到不同判断批次。

若某 selected industry 没有 runtime candidate，记录 `NO_RUNTIME_CANDIDATE`；这不是 FAILED，也不自动用第 4 个行业替换。

---

## 5. Fresh Transaction / Frozen Ledger

每次触发必须生成新 `run_id`。

`research/pre_research_ledger.json` 只用于当前 invocation：

1. 先写 `BUILDING`；
2. 记录本轮正式文件 blob SHA、trade_date、selected_industry_codes；
3. 完成 selected-industry 全部 Stage A 后一次性写 `FROZEN`；
4. 下一次触发必须重建，不得 resume。

Stage A 期间禁止公司级外部 Web 研究。

---

## 6. Stage A｜Structured Screening

从这里开始完全沿用原低风险流程。

只处理 selected industries 的全部 runtime candidates：

1. `PEER_DOMINATED`；
2. 未被支配者进入 `CLEARLY_WEAK / PASS_TO_DEEP_RESEARCH / UNCERTAIN`；
3. 每只公司恰好一个 ledger entry；
4. 不得 Top N、不设行业配额、不因为已有好公司提前停止；
5. Stage A 防漏优先。

完成条件：

```text
stage_a_processed_codes == selected_industry_runtime_candidate_codes
```

然后冻结 Ledger，派生 `deep_read_codes = PASS + UNCERTAIN`。

---

## 7. Stage B｜Research Worthiness Gate

Frozen Ledger Hard Gate 通过后，对全部 `deep_read_codes` 按 `SKILL.md` 原规则执行：

```text
Q1 核心盈利可信度
→ Q2 安全边际粗筛
→ 必要时 Q2-lite
→ deep_research_required_codes
```

Gate 是研究预算分配，不是排名。

不得引入新的行业门、资金门、lifecycle、activation tier 或 Top N。

Gate coverage 必须完整闭合。

---

## 8. Deep Research

必须穷尽 `deep_research_required_codes`，完全沿用原规则。

允许分 batch，但 batch 只用于执行，不具有排名/淘汰意义。

公司终态只允许：

- `confirmed`
- `waiting_for_entry`
- `research_uncertain`
- `excluded`

当前价格不好只能进入 `waiting_for_entry`，不能仅因价格不好 `excluded`。

coverage 未闭合时不得主动结束或发布正式榜。

---

## 9. Unified Entry Evaluation / Risk Cluster / 价格纪律

完全沿用原流程：

- 正常化盈利区间；
- 可辩护的保守估值；
- conservative fair value；
- `conservative_upside` 原则上 `>= 15%`；
- 当前价原则上距离最终安全区约 5% 以内，或存在同等可量化下行保护；
- Risk Cluster 只在 Stage B 与 Deep Research coverage 完成后做发布层去相关；
- 不反向修改公司研究状态。

正式输出保留：

```text
股票｜行业｜状态｜当前价｜合理买入区间｜低风险买入区间｜失效价/条件｜第一阻力位｜核心逻辑｜核心风险
```

无可靠低风险区间写 `N/A`，不得制造价格。

---

## 10. 正式输出与漏斗

### A.【今日行业入口】

只说明从 `industry_state.json` 选出的最多 3 个行业：

```text
行业｜景气/盈利摘要｜资金集中摘要｜为什么进入今日入口
```

### B.【A股低风险买点榜】

按原低风险流程输出。

### C.【筛选漏斗】

至少给出：

- `industry_state` 行业总数；
- 原盈利/可研究行业池数量；
- selected industries 数量；
- selected industries 对应 runtime candidate 数；
- Stage A PASS / UNCERTAIN 数；
- Gate 后 Deep Research 数；
- confirmed / waiting / uncertain / excluded 数。

---

## 11. 不变原则

> **唯一变化：把原来的“所有盈利行业一起下钻”缩成“先从这些行业中选最近景气 + 资金集中的 3 个，再下钻”。**

> **行业入口只缩小搜索空间，不替代原个股研究。**

> **Stage 0 不做公开行业深研。**

> **Stage A / Stage B / Deep Research / 估值 / Risk Cluster 不因入口变化而重写。**

> **没有客观 Hard Gate 失败时，模型没有主动 FAILED / STOPPED_EARLY 的权限。**
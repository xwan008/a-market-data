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

`research/latest_formal_result.json` 仅用于把**已经完整完成的正式收盘研究结果**交给次日 07:00 早间版；它不是 Stage A / Stage B 的历史缓存，也不得用于下一轮正式版跳过任何研究步骤。

---

## 1. 正式输入

### 1.1 19:00 收盘正式版 / 手动正式版

每次读取当前 `main`：

- `skill/RUNTIME_READ_PROTOCOL.md`
- `skill/SKILL.md`
- `data/runtime/meta.json`
- `meta.screening_group_file`
- `meta.candidate_file`
- `data/research/industry_state.json`

每次触发都是新的独立事务，不复用上一轮 Stage A / Gate / Deep Research 结论。

### 1.2 07:00 早间版

早间版读取：

- `skill/RUNTIME_READ_PROTOCOL.md`
- `research/latest_formal_result.json`
- 当前最新有效正式收盘 `data/runtime/meta.json`（只用于校验 trade_date / runtime 身份，不重新选股）

早间版不得把 `latest_formal_result.json` 当作新的正式选股运行输入；它只用于隔夜风险检查与昨日计划的确认/降级/失效提示。

---

## 2. Bootstrap / Runtime Hard Gate

19:00 / 手动正式版必须确认：

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

## 11. 正式结果持久化｜19:00 / 手动正式版成功后的唯一交接

### 11.1 持久化文件

唯一正式交接文件：

```text
research/latest_formal_result.json
```

它保存**最近一次完整成功的正式版结果**，供次日 07:00 使用。

它不得被 Stage A / Gate / Deep Research 用于跳过、恢复、缓存或复用公司研究结论。

### 11.2 只有完整成功才能覆盖

只有同时满足以下条件，才允许写入/覆盖 `latest_formal_result.json`：

```text
runtime_hard_gate = PASSED
stage_a_coverage = COMPLETE
stage_b_gate_coverage = COMPLETE
deep_research_coverage = COMPLETE
publication_ready = true
```

FAILED / INCOMPLETE / UNVERIFIED / coverage 未闭合的运行**绝不能覆盖上一份 COMPLETE 文件**。

因此昨晚正式版失败时，早间版仍可继续读取更早一份仍有效的 COMPLETE 结果；不得用失败半成品替换它。

### 11.3 最小正式结构

`latest_formal_result.json` 至少包含：

```json
{
  "schema_version": 1,
  "result_kind": "a_share_low_risk_formal_result",
  "status": "COMPLETE",
  "trade_date": "YYYY-MM-DD",
  "run_id": "...",
  "published_at": "...+08:00",
  "source_runtime_trade_date": "YYYY-MM-DD",
  "source_runtime_commit_sha": "...",
  "selected_industries": [
    {
      "code": "...",
      "name": "...",
      "prosperity_summary": "...",
      "fund_concentration_summary": "..."
    }
  ],
  "confirmed": [],
  "waiting_for_entry": [],
  "research_uncertain": [],
  "excluded": [],
  "funnel": {}
}
```

每个 `confirmed` / `waiting_for_entry` 至少保存：

- `code`
- `name`
- `industry_code`
- `industry_name`
- `status`
- `current_price`
- `reasonable_price_range`
- `low_risk_buy_range`
- `invalidation_price_or_condition`
- `first_resistance`
- `primary_profit_driver`
- `dominant_risk_factor`
- `core_logic`
- `core_risk`

`research_uncertain` / `excluded` 可以保存精简审计信息，但不得伪装成早间可执行候选。

### 11.4 写入顺序与并发保护

正式版完成公司研究与价格阶梯后：

1. 构造完整 `latest_formal_result.json`；
2. 若文件不存在则 create；存在则先读取当前 blob SHA 再 update；
3. 写入后立即回读；
4. 校验 `status == COMPLETE`、`trade_date`、`run_id`、selected industries、confirmed/waiting 集合与本轮最终结果一致；
5. 校验通过后，才认为正式版的“发布 + 次日交接”事务 COMPLETE。

如果发生写入冲突，必须先重新读取当前文件：

- 若当前文件已经是**更晚 trade_date / 更晚正式 run** 的 COMPLETE 结果，不得回退覆盖；
- 若当前文件仍是旧结果，可以用最新 SHA 重试一次；
- 仍失败则记录 `FORMAL_RESULT_PERSISTENCE_FAILED`，不得声称早间交接已完成。

---

## 12. 07:00 早间版｜只做隔夜检查，不重新选股

### 12.1 交接 Hard Gate

07:00 首先读取 `research/latest_formal_result.json`，要求：

```text
result_kind == a_share_low_risk_formal_result
status == COMPLETE
trade_date == 当前最新有效正式收盘 runtime.trade_date
source_runtime_trade_date == trade_date
selected_industries 可解析且数量 1..3
confirmed / waiting_for_entry 可解析
```

如果文件缺失、`EMPTY`、非 COMPLETE、trade_date 与当前最新有效正式收盘不一致或结构损坏：

```text
MORNING_HANDOFF_UNAVAILABLE
```

此时只说明缺少有效正式交接，**不得**从 runtime candidates 重新推测昨日 selected industries / confirmed / waiting，也不得启动 Stage 0 / Stage A / Deep Research。

### 12.2 早间只允许检查什么

早间版只围绕上一份 COMPLETE 结果中的：

- `selected_industries`
- `confirmed`
- `waiting_for_entry`

检查隔夜公开变量是否改变原判断，例如：

- 对应商品价格 / 价差；
- 海外同产业链公司表现；
- 美元指数、美债收益率；
- Nasdaq / 半导体等相关海外风险资产；
- 中国资产海外表现；
- 重大政策、公司公告、产业突发事件。

输出只允许：

- `NORMAL`：没有足以改变昨日计划的新信息；
- `CAUTION`：出现需要降低执行积极性或等待确认的新风险；
- `RISK_OFF`：出现直接触发昨日失效逻辑或显著破坏核心假设的新信息。

早间版不得产生新的正式 selected industries、不得新增股票、不得重算完整估值、不得把 waiting 自动升级为 confirmed；真正的新选股与状态重建留给下一次正式版。

---

## 13. 不变原则

> **唯一选股逻辑变化：把原来的“所有盈利行业一起下钻”缩成“先从这些行业中选最近景气 + 资金集中的 3 个，再下钻”。**

> **正式结果持久化只解决 19:00 → 07:00 状态交接，不改变任何选股判断。**

> **行业入口只缩小搜索空间，不替代原个股研究。**

> **Stage 0 不做公开行业深研。**

> **Stage A / Stage B / Deep Research / 估值 / Risk Cluster 不因入口变化或持久化机制而重写。**

> **失败/未完成正式版永不覆盖上一份 COMPLETE 结果。**

> **07:00 只读取 COMPLETE 结果做隔夜风险检查，不重新选股。**

> **没有客观 Hard Gate 失败时，模型没有主动 FAILED / STOPPED_EARLY 的权限。**

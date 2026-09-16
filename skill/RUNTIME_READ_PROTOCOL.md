# A股低风险买点榜｜运行时执行协议

本文件是唯一正式执行契约。每次正式执行必须遵守：

> **Stage 0 先从全行业识别 T1/T2 并直选 3 个行业 → 只在这 3 个行业对应的 runtime 候选中执行旧版 Stage A / Stage B / Deep Research → 最终价格阶梯。**

不得再使用版本化 V4/V5/V6 生命周期门、行业预资格门或兼容分支。

---

## 1. 正式输入

每次 19:00 收盘正式版或手动正式触发，读取当前 `main`：

- `skill/RUNTIME_READ_PROTOCOL.md`
- `skill/SKILL.md`
- `data/runtime/meta.json`
- `meta.screening_group_file`
- `meta.candidate_file`
- `data/research/industry_state.json`

公开 Web 研究只在 Stage 0 行业研究和 Stage B 之后允许使用；Stage A 公司筛选必须 repository-only。

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
- runtime 使用正式旧版结构筛选字段：`structure_tier / strong_support / strong_volume_zone`。

不存在 `industry_first_pool_applied`、`stock_lifecycle_gate_applied`、`selection_mode=industry_first_leading_prosperity_then_stock` 等额外硬门要求。

Hard Gate 失败才允许整轮 FAILED。

---

## 3. Stage 0｜全行业 T0/T1/T2 入口

### 3.1 行业扫描范围

Stage 0 从 `data/research/industry_state.json` 的完整申万三级行业集合开始，不能从 runtime 股票候选反推行业。

先利用仓库结构化事实建立全行业扫描底稿，再针对最有希望的产业方向查询公开资料，完成 `SKILL.md` 定义的两条独立证据链：

1. 产业链：T0 / T1 / T2；
2. 市场链：新异动 / 候选趋势 / 趋势确认 / 高潮衰退 / 失效。

### 3.2 只选 3 个行业

正式入口只接受 T1 / T2。

优先：

```text
T1 + 候选趋势
T1 + 趋势确认但未过热
T2 + 候选趋势
T2 + 趋势确认但未过热
```

从有效方向中直选 3 个，生成：

```text
selected_industry_codes
selected_industry_names
```

若有效 T1/T2 少于 3 个，则按实际数量；不得用 T0 凑数。

### 3.3 行业层在此结束

固定 selected industries 后：

- 不得再使用产业状态、资金标签、行业成交量门槛继续删除公司；
- 后续 Stage A / Stage B 只研究 selected industries 中已经存在于正式 runtime 的候选；
- 若某 selected industry 在 runtime 中没有候选，明确记录 `NO_RUNTIME_CANDIDATE`，不替换为第 4 个行业，除非 Stage 0 本身判断第 3 个行业无效。

---

## 4. screening_group 消费规则

`screening_group_file` 是 Stage A 正式工作视图。

按 meta 中 `screening_group_serialization.line_count` 使用 40 行有界区间完整读取；不得依赖一次整文件返回。

完整读取后，只保留 `industry_code in selected_industry_codes` 的完整申万三级组作为本轮 Stage A universe。

一个行业组不可拆分到不同判断批次。

---

## 5. Fresh Transaction / Frozen Ledger

每次触发必须生成新 `run_id`。

`research/pre_research_ledger.json` 只用于当前 invocation：

1. 先写 `BUILDING`；
2. 记录本轮正式文件 blob SHA、trade_date、selected_industry_codes；
3. 完成全部 selected-industry Stage A 后一次性写 `FROZEN`；
4. 下一次触发必须重建，不得 resume。

Stage A 期间禁止公司级外部 Web 研究。

---

## 6. Stage A｜Structured Screening

只处理 selected industries 的全部 runtime candidates。

按 `SKILL.md`：

1. 先做 `PEER_DOMINATED`；
2. 未被支配者做 `CLEARLY_WEAK / PASS_TO_DEEP_RESEARCH / UNCERTAIN`；
3. 每只公司恰好一个 ledger entry；
4. 不得 Top N、不设行业配额、不因为已有好公司提前停止。

完成条件：

```text
stage_a_processed_codes == selected_industry_runtime_candidate_codes
```

然后冻结 Ledger，派生 `deep_read_codes`。

若 selected industries 中 runtime 候选为 0，则正式输出“行业选中但当前无旧版低风险结构候选”，不是 FAILED。

---

## 7. Stage B｜Research Worthiness Gate

对 Frozen Ledger 的全部 `deep_read_codes` 执行：

```text
Q1 核心盈利可信度
→ Q2 安全边际粗筛
→ 必要时 Q2-lite
→ deep_research_required_codes
```

Gate 必须使用 `SKILL.md` 的固定规则，不允许重新引入 lifecycle / activation tier / industry money gate。

Gate coverage 必须完整闭合。

---

## 8. Deep Research

必须穷尽 `deep_research_required_codes`。

每家公司研究真实主营、盈利驱动、行业到公司的传导、盈利质量、周期位置、风险与正常化估值。

允许分批执行，但 batch 不具有排名/淘汰意义。

Deep Research 终态只允许：

- `confirmed`
- `waiting_for_entry`
- `research_uncertain`
- `excluded`

coverage 未闭合时不得提前发布正式榜。

---

## 9. Risk Cluster / 正式榜

只有：

```text
stage_a_coverage = COMPLETE
stage_b_gate_coverage = COMPLETE
deep_research_coverage = COMPLETE
```

才允许发布。

Risk Cluster 只在最终发布层去相关，不反向修改公司研究状态。

正式输出三部分：

### A.【今日行业入口】

```text
行业｜产业阶段(T1/T2)｜市场阶段｜核心正向证据｜反向证据
```

固定最多 3 个。

### B.【A股低风险买点榜】

```text
股票｜行业｜状态｜当前价｜合理买入区间｜低风险买入区间｜失效价/条件｜第一阻力位｜核心逻辑｜核心风险
```

### C.【筛选漏斗】

至少给出：

- 全行业扫描数量；
- T1/T2 有效行业数量；
- selected industries = 3 或实际数量；
- selected industries 对应 runtime candidate 数；
- Stage A PASS / UNCERTAIN 数；
- Gate 后 Deep Research 数；
- confirmed / waiting / uncertain / excluded 数。

---

## 10. 价格纪律

当前价使用 runtime 对应 `trade_date` 收盘价。

价格区间综合：

- 正常化盈利和保守估值；
- MA20 / MA60；
- 支撑；
- 成交密集区；
- 最近阻力；
- invalidation。

没有可辩护低风险区间写 `N/A`。

当前价高于合理区间上沿，不得作为立即执行机会。

---

## 11. 禁止漂移

正式主线禁止重新加入：

- activation tier / lifecycle 硬门；
- EARNINGS_TRANSMITTING / FUNDS_ATTENTION 等额外选股资格层；
- 5% 回撤一刀切；
- 绝对量比单一资金门；
- 先个股再反推行业；
- V4 / V4.1 / V5 / V6 等版本分支；
- 为了凑榜单改变规则。

今后的修改应直接修改本主线，不再新增并行版本。

# A股低风险买点榜｜模型判断规则

## 1. 目标

目标仍然是：

> **寻找基本面没有明显恶化，经过价值与价格结构双重验证后具备安全边际，向下剩余空间有限，而未来 1–2 个季度保守上行空间充足的 A 股公司。**

核心原则：

> **先看还能跌多少，再看能涨多少。**

当前主线有两处明确调整：

1. 原来从全部盈利/可研究行业一起下钻；现在先选“最近景气仍好 + 资金正在集中”的最多 3 个行业；
2. Stage A 前不再用 `PE<=30`、`股价<=120`、旧低位结构规则提前删除公司。真正的估值与买点判断回到 Stage A、Stage B 和最终 Entry Evaluation。

除此之外，Structured Screening、Stage B Gate、Deep Research、估值、Risk Cluster 与最终安全区规则不变。

---

## 2. Stage 0｜行业入口只做缩圈

Stage 0 只读取 `data/research/industry_state.json`，不做公开行业深研。

原盈利/可研究行业资格：

```text
trend == improving
OR
(trend == stable AND breadth in {broad, divergent})
```

从中只使用 JSON 已有字段，优先选择盈利/景气仍改善，同时市场确认更强、活跃度提升、上涨广度扩散、相对量能增强的最多 3 个行业。

固定 `selected_industry_codes` 后行业层结束；后续不得再用行业景气、资金、生命周期标签机械删除公司。

---

## 3. Stage A 前程序事实｜宽准入，不提前替模型做估值

程序只保留真正的硬研究资格：

- 非 ST；
- 有效正价格；
- `net_profit > 0`；
- report / valuation context / 趋势 / 60日结构数据完整；
- 不满足严重收入利润双杀排除条件；
- 所属行业属于原盈利/可研究行业池。

以下旧条件全部降为**非硬门事实**：

- `PE > 30`；
- `price > 120`；
- 60日位置高于 35%；
- 未满足旧支撑/成交密集区组合条件。

程序对旧低风险结构只输出：

```text
READY_STRUCTURE
WATCH_STRUCTURE
```

含义：

- `READY_STRUCTURE`：旧低位结构条件已经满足，是价格结构上的正向证据；
- `WATCH_STRUCTURE`：当前结构尚不够理想，需要 Stage A / Gate / 最终 Entry Evaluation 继续判断，但**不代表公司不值得研究**。

因此：

> **结构标签回答“现在的价格结构有多舒服”，不回答“这家公司是否有资格进入研究”。**

原 30 倍 PE、120 元股价仅保留为诊断参考，不具有一票否决权。

---

## 4. Structured Screening / Model Prescreen

Stage A 只处理 `selected_industry_codes` 对应的完整 screening groups，并覆盖其中全部 `READY_STRUCTURE + WATCH_STRUCTURE` 候选。

### 4.1 同行明确支配

在每个申万三级行业组内，多只公司只比较：

- 价格结构；
- 估值质量；
- 经营质量。

A 只有在存在 B 且同时满足时，才允许 `PEER_DOMINATED`：

1. B 在价格结构、估值质量、经营质量三个维度没有一个明显弱于 A；
2. B 至少一个维度明显更优；
3. A 没有 B 无法覆盖的明显差异化优势；
4. 不存在业务异质性、周期失真或数据冲突，需要公开研究才能判断。

只要互有胜负、不可比或不确定，就不得做同行支配淘汰。

不得用 `PEER_DOMINATED` 表达 Top N、同行太多、风险簇压缩或研究预算不足。

### 4.2 公司绝对质量

未被同行支配的公司只允许：

- `CLEARLY_WEAK`
- `PASS_TO_DEEP_RESEARCH`
- `UNCERTAIN`

单一 PE、股价绝对值、`WATCH_STRUCTURE`、ROE、利润增长、负现金流、行业状态或单个质量标签均不得一票淘汰。

多个彼此独立的负向事实，可以与价格结构、估值和经营趋势共同支持 `CLEARLY_WEAK`。

若周期、会计口径或业务结构可能实质改变判断，使用 `UNCERTAIN`。

Stage A 防漏优先。

### 4.3 价格不好 ≠ 公司不值得研究

如果公司基本面和研究价值成立，但当前：

- PE 偏高；
- 位置偏高；
- 支撑较远；
- 尚未回到低风险区；

不得因为这些事实在 Stage A 提前删除。它可以继续进入 Stage B / Deep Research，并最终落到 `waiting_for_entry`。

### 4.4 完整 Ledger

每只候选恰好一个 `ledger_entry`：

```text
code / result / reason_code / reason
```

`result` 只能是：

```text
PEER_DOMINATED
CLEARLY_WEAK
PASS_TO_DEEP_RESEARCH
UNCERTAIN
```

`PASS_TO_DEEP_RESEARCH + UNCERTAIN` 派生 `deep_read_codes`。

禁止综合评分、Top N、机械 Top1/Top2、行业配额、找到几只好公司后提前停止。

---

## 5. Stage B｜Research Worthiness Gate

Gate 仍只回答：

> **Q1：正常化后的核心盈利是否可信、可持续？**

> **Q2：如果核心盈利可信，以当前价格粗看，是否仍有可能形成低风险安全边际？**

默认原则：

> **只有明确 No 才 Gate-filter；信息不足、边界或可解释，一律继续。**

Gate 不允许综合评分、Top N、行业配额或相对排名。

### 5.1 Q1 硬门

满足任一条件才允许 `gate_filtered_q1`：

```text
1. net_profit_yoy < 0 AND deduct_basic_eps_yoy < 0
2. net_profit_yoy >= 20 AND deduct_basic_eps_yoy <= -10
3. quality_flag.profit_growth_cashflow_negative == true
   AND (deduct_basic_eps_yoy is null OR deduct_basic_eps_yoy <= 0)
4. net_profit_yoy >= 50
   AND deduct_basic_eps_yoy is not null
   AND deduct_basic_eps_yoy <= 5
```

### 5.2 Q2 粗筛

定义：

```text
min_positive_pe = min(pe_ttm, pe_dynamic) among positive values
normalized_pe_proxy = max(pe_ttm, pe_dynamic) among positive values
```

若没有可用正 PE，不因 Q2 机械淘汰。

满足任一条件才允许 `gate_filtered_q2`：

```text
1. pe_ttm > 25 AND pe_dynamic > 25
   AND deduct_basic_eps_yoy < 20
   AND roe < 8

2. min_positive_pe > 22
   AND deduct_basic_eps_yoy <= 5
   AND roe < 8

3. normalized_pe_proxy > 20
   AND roe < 5
   AND deduct_basic_eps_yoy is not null
   AND deduct_basic_eps_yoy < 20
```

注意：研究准入层取消 PE30 硬门，**不等于取消估值纪律**。估值正式在 Q2 与最终 Entry Evaluation 处理。

### 5.3 Q2-lite

只在估值边界或利润异常时允许 1–2 次公司级定向查询，确认归母/扣非、一次性收益、联营/投资收益。

只有高置信度确认非经常性收益或投资收益主导、导致表面低估值明显失真时，才允许 `gate_filtered_q2_lite`。

Q2-lite 不扩张成完整产业链或目标价研究。

Gate 全覆盖后派生：

```text
gate_filtered_q1_codes
gate_filtered_q2_codes
gate_filtered_q2_lite_codes
deep_research_required_codes
```

---

## 6. Deep Research

对全部 `deep_research_required_codes` 完整研究，不设 Top N 配额。

至少确认：

1. 真实主营、主要产品和业务；
2. `primary_profit_driver`；
3. `dominant_risk_factor`；
4. 未来 1–2 个季度盈利逻辑是否可验证；
5. 行业→公司传导是否成立；
6. 收入、扣非、现金流、毛利率异常如何解释；
7. 一次性收益是否重大；
8. 是否处于周期盈利高点；
9. 至少一条最可能推翻当前判断的反向证据。

Deep Research 可以分 batch，但 batch 只具有执行意义，不具有投资比较、配额、排名或淘汰意义。

---

## 7. Research Support Test + Unified Entry Evaluation

先判断研究逻辑：

- 被实质反证 → `excluded`
- 一次定向补查后仍存在实质缺口/冲突 → `research_uncertain`
- 研究逻辑成立 → 进入 Unified Entry Evaluation

只有 `research_supported = true` 的公司进入统一 Entry Evaluation：

```text
正常化盈利区间
→ 正常化盈利中枢
× 可辩护的保守估值
→ conservative_fair_value / 最终安全区
→ conservative_upside
→ current_price 与 low_risk_buy_range 的关系
→ entry_ready
```

原则：

1. 强周期公司必须使用正常化盈利；
2. 正式 conservative fair value 默认采用“正常化盈利区间中枢 × 可辩护保守估值”；
3. 盈利下沿 × 估值下沿只作 stress floor；
4. 原则上 `conservative_upside >= 15%`；
5. 原则上当前价距离最终安全区约 5% 以内，或有同等强度、可量化下行保护。

映射：

```text
entry_ready = true  → confirmed
entry_ready = false → waiting_for_entry
```

因此，`WATCH_STRUCTURE`、高 PE、较高价格位置最终完全可以合理落到 `waiting_for_entry`，而不是在研究前消失。

---

## 8. Risk Cluster Consolidation

只有 Stage B Gate 与 Deep Research coverage 全部完成后，才执行 Risk Cluster。

归簇主要看：

- `primary_profit_driver` 是否高度重合；
- 上涨催化是否依赖同一关键变量；
- 最重要反向风险是否会由同一变量同时触发。

不得按申万行业代码机械归并。

同一风险簇多家公司都 `confirmed` 时，公司状态保持不变；正式榜可选 representative，其余作为 alternatives。

---

## 9. 最终估值与价格阶梯

Stage A 前的结构标签不是最终价值底。

Deep Research 后尽量形成：

- `reasonable_price_range`
- `base_fair_value`
- `low_risk_buy_range`
- `conservative_upside`
- `downside_to_safety_zone`
- `hard_risk_boundary`
- 第一阻力位

最终安全区综合正常化盈利、保守估值、PE/PB 与 ROE/增长/现金流匹配、重要支撑、前期低点和成交密集区。

无可靠低风险买入区间时写 `N/A`，不得制造价格。

---

## 10. 不变原则

> **程序负责真正的硬资格和结构化事实，模型负责关系和解释。**

> **行业入口只负责从原盈利/可研究行业中选最近景气 + 资金集中的最多 3 个。**

> **PE30、股价120、旧低位结构不再是 Stage A 前硬门。**

> **`READY_STRUCTURE / WATCH_STRUCTURE` 只是价格结构上下文。**

> **Stage B Q2 与最终正常化估值继续维持低风险纪律。**

> **公司值得研究但当前价格不好，应进入 `waiting_for_entry`，而不是在 runtime 被删除。**

> **Gate-filtered 不伪装成完整 Deep Research 四终态。**

> **Batch 只用于执行分包，不用于投资比较、配额或组内淘汰。**

> **完整 Deep Research 公司状态只走 Research Support Test → Unified Entry Evaluation → 四状态映射。**

> **Risk Cluster 只在发布层去相关。**

> **正式机会集合不设 Top N、目标数量或固定上限。**

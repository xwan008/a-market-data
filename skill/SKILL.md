# A股低风险买点榜｜模型判断规则

## 1. 唯一目标

寻找：

> **先找到当前真正处于 T1 / T2 的产业方向，从中直选 3 个最值得研究的行业；然后只在这 3 个行业里，按原低风险流程寻找基本面可信、价格处于低风险结构、未来 1–2 个季度有足够保守上行空间的公司。**

核心原则：

> **行业入口只回答“今天去哪里找”；个股流程回答“在这里买谁、什么价格买”。**

行业入口完成后，不得继续用行业标签机械删除个股；个股必须回到公司自身的价格结构、盈利质量、估值和研究证据上判断。

---

## 2. Stage 0｜行业入口：T0 / T1 / T2 + 独立市场链

### 2.1 两条证据链必须独立

**产业链**回答：未来 1–2 个季度盈利为什么可能改善？

优先证据：

- 产品价格 / 价差；
- 库存与供需；
- 订单、排产、稼动率；
- 终端需求；
- 产能、资本开支；
- 原料成本与传导；
- 政策、招投标、出货；
- 最新财报 / 业绩预告对趋势的验证。

产业状态：

- `T0`：出现拐点线索，但未来盈利传导仍不足以确认；
- `T1`：准景气确认。已有明确第一锚，能够合理解释未来 1–2 个季度收入/利润改善，但财报可以尚未完全兑现；
- `T2`：正式景气。产业逻辑与盈利兑现均已有较强证据。

**市场链**回答：A股是否已经开始交易这条逻辑？

观察：

- 行业相对指数强度；
- 上涨广度和中位股表现；
- 成交扩张；
- 龙头与中票是否扩散；
- 第一次分歧是否有承接。

市场状态：

`新异动/观察 → 候选趋势 → 趋势确认 → 高潮/衰退 → 失效`

产业状态不得由股价上涨反推；市场状态也不得由财报好坏替代。

### 2.2 直选 3 个行业

正式入口只接受 `T1 / T2`。

优先顺序：

1. `T1 + 候选趋势`；
2. `T1 + 趋势确认但未过热`；
3. `T2 + 候选趋势`；
4. `T2 + 趋势确认但未过热`。

从当前有效 T1/T2 中直选 **3 个行业**。若有效行业不足 3 个，按实际数量，不允许用 T0 凑数。

选完后固定 `selected_industry_codes`。从这一刻起，行业层任务结束；后续只允许在这 3 个行业对应的 runtime 候选中运行 Stage A / Stage B。

---

## 3. Stage A｜Structured Screening

Stage A 使用锁定 runtime 的结构化事实，不做公司级外部研究。

程序已经完成确定性 Eligibility / Structure Filter，包括价格位置、支撑、成交密集区、估值/盈利基础和申万三级分组。Stage A 只处理 `selected_industry_codes` 对应的完整 screening groups。

### 3.1 同行明确支配

多只公司同组比较：

- 价格结构；
- 估值质量；
- 经营质量。

A 只有在存在 B 且 B 三个维度均不明显弱于 A、至少一项明显更优、A 无不可替代优势、也不存在需要公开研究才能解释的关键差异时，才可 `PEER_DOMINATED`。

禁止机械 Top1/Top2、行业配额、综合打分或为了压缩研究数量而做同行淘汰。

### 3.2 公司绝对质量

未被同行支配的公司只允许：

- `CLEARLY_WEAK`：多个独立结构化事实共同显示明显弱，且无确定性反向优势；
- `PASS_TO_DEEP_RESEARCH`：有明确继续研究价值；
- `UNCERTAIN`：真实业务/周期/会计口径等可能实质改变结论，结构化事实无法可靠解释。

单一 PE、ROE、负现金流、利润增速或单个标签不得一票淘汰。

Stage A 防漏优先。

---

## 4. Stage B｜Research Worthiness Gate

`PASS_TO_DEEP_RESEARCH + UNCERTAIN` 形成 `deep_read_codes`。

Gate 只回答：

- Q1：正常化核心盈利是否可信？
- Q2：如果盈利可信，当前价格是否仍可能形成低风险安全边际？

默认：**只有明确 No 才 Gate-filter；边界和信息不足继续 Deep Research。**

### 4.1 Q1 硬门

满足任一条件才允许 `gate_filtered_q1`：

```text
1. net_profit_yoy < 0 AND deduct_basic_eps_yoy < 0
2. net_profit_yoy >= 20 AND deduct_basic_eps_yoy <= -10
3. profit_growth_cashflow_negative == true
   AND (deduct_basic_eps_yoy is null OR deduct_basic_eps_yoy <= 0)
4. net_profit_yoy >= 50
   AND deduct_basic_eps_yoy is not null
   AND deduct_basic_eps_yoy <= 5
```

### 4.2 Q2 粗筛

定义：

```text
min_positive_pe = min(pe_ttm, pe_dynamic) among positive values
normalized_pe_proxy = max(pe_ttm, pe_dynamic) among positive values
```

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

无可用正 PE 时不得因 Q2 机械淘汰。

### 4.3 Q2-lite

只在估值边界或利润异常时允许 1–2 次定向查询，确认归母/扣非、一次性收益、联营/投资收益。只有高置信度确认非经常性收益或投资收益主导、导致表面低估值明显失真时，才允许 `gate_filtered_q2_lite`。

Gate 是研究预算分配，不是排名。

---

## 5. Deep Research

对全部 `deep_research_required_codes` 完整研究，不设 Top N 配额。

至少确认：

1. 真实主营与主要产品；
2. `primary_profit_driver`；
3. `dominant_risk_factor`；
4. 未来 1–2 个季度盈利逻辑；
5. 行业逻辑如何传导到公司；
6. 收入、扣非、现金流、毛利率异常如何解释；
7. 一次性收益是否重大；
8. 是否位于周期盈利高点；
9. 至少一条最可能推翻判断的反向证据。

四个终态：

- `confirmed`：研究逻辑成立，且当前具备低风险安全边际；
- `waiting_for_entry`：研究逻辑成立，但当前价格不满足入场条件；
- `research_uncertain`：一次定向消歧后仍有会实质改变结论的事实缺口；
- `excluded`：研究逻辑被实质反证。

当前价格不好只能 `waiting_for_entry`，不能因此 `excluded`。

---

## 6. Unified Entry Evaluation

只对 `research_supported = true` 的公司做统一入场评估：

```text
正常化盈利区间
→ 正常化盈利中枢
× 可辩护保守估值
→ conservative_fair_value
→ conservative_upside
→ current_price 与最终安全区关系
→ entry_ready
```

强周期公司必须使用正常化盈利，禁止高景气利润机械年化。

原则：

- `conservative_upside >= 15%`；
- 当前价原则上距离最终低风险安全区约 5% 以内，或存在同等强度、可量化的下行保护。

程序 Structure Filter 只是“值得研究”，不是最终价值底。

---

## 7. Risk Cluster Consolidation

只有 Stage B 和 Deep Research coverage 全部闭合后才做。

按 `primary_profit_driver`、共同催化和共同反向风险归簇，不按申万行业机械去重。

多家公司都满足 `entry_ready` 时，先全部保持 `confirmed`；发布时再按风险簇呈现独立风险收益机会。

---

## 8. 最终价格阶梯

每只正式机会必须给出：

```text
股票｜行业｜状态｜当前价｜合理买入区间｜低风险买入区间｜失效价/条件｜第一阻力位｜核心逻辑｜核心风险
```

- 当前价：正式 runtime 对应交易日收盘价；
- 合理买入区间：结合正常化价值、MA、支撑、成交密集区和风险收益；
- 低风险买入区间：更保守，靠近最终安全区/可靠承接；无可靠依据写 `N/A`；
- 失效位：优先结构 invalidation / 明确基本面失效条件，不使用任意固定百分比；
- 第一阻力位：使用正式价格结构最近阻力。

当前价高于合理买入区间上沿，不得标记为可立即执行机会。

---

## 9. 主线自检

每次正式发布必须依次回答：

1. 今天为什么选择这 3 个 T1/T2 行业？
2. 这 3 个行业里有哪些 runtime 候选？是否完整进入 Stage A？
3. 哪些公司被同行明确支配或绝对质量淘汰？
4. Gate 为什么留下/过滤每家公司？
5. Deep Research 后哪些公司研究逻辑成立？
6. 当前价格是否真正具备安全边际？
7. 什么条件会证明判断错误？

禁止重新引入额外版本化 lifecycle 标签、行业预资格层或为了凑榜单而修改标准。

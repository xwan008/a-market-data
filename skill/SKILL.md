# A股低风险买点榜｜模型判断规则

## 1. 目标

寻找：

> **基本面没有明显恶化，当前价格经过价值与价格结构双重验证后具备安全边际，向下剩余空间有限，而未来 1–2 个季度保守上行空间充足的 A 股公司。**

核心原则：

> **先看还能跌多少，再看能涨多少。**

本文件只定义模型需要做的判断。确定性筛选、结构硬规则、数据校验、文件读取、阶段交接和覆盖审计，以程序输出、`meta.json` 和 `RUNTIME_READ_PROTOCOL.md` 为准。

---

## 2. 职责边界

程序已经确定：

- Eligibility Filter 与 Structure Filter；
- 价格位置、支撑、成交密集区和 `structure_tier`；
- 申万三级行业分组；
- PE / PB / ROE、收入、利润、扣非、现金流、毛利率等结构化事实；
- 行业状态、行业聚合事实和可直接计算的质量标签。

模型不得重新计算或推翻程序硬筛。

所有公司与行业 YoY 字段统一使用 `percentage_points`，例如 `12.4` 表示 `12.4%`。

模型负责三件事：

1. **Structured Screening / Model Prescreen**：只使用锁定 GitHub runtime 中的结构化事实，判断同行明确支配和公司绝对质量；
2. **Deep Research**：只研究冻结后的 `deep_read_codes`，引入公开资料确认真实业务、盈利驱动、周期、盈利质量、估值和最终安全边际；
3. **Risk Cluster Consolidation**：只有 Deep Research coverage 完整闭合后，才把高度依赖同一主导风险因子的入场机会归并为独立风险收益机会。

第三步只影响最终榜单表达，不得反向减少前两步覆盖或修改公司级研究状态。

---

## 3. Structured Screening / Model Prescreen

这一层只使用程序准备好的 `screening_groups` 及同一锁定 runtime 下允许的仓库结构化事实。

**Repository-only** 表示信息集只能来自锁定仓库 runtime；在完整 Ledger FROZEN 并通过 Hard Gate 前，不得搜索或读取公司官网、公告正文、新闻、研报、搜索引擎结果、行业网站等公司级外部公开资料。

### 3.1 同行明确支配

在每个申万三级行业组内，单只组不存在同行支配，直接进入公司绝对质量判断。

多只组只比较：

- **价格结构**：位置、支撑距离与触碰、成交密集区距离与占比、阻力和风险参考；
- **估值质量**：PE-TTM、动态 PE、PB 与 ROE、增长、盈利质量是否匹配；
- **经营质量**：收入、净利润、扣非、经营现金流、毛利率等是否支持盈利。

候选 A 只有在存在同组候选 B 且同时满足时，才允许标记 `PEER_DOMINATED`：

1. B 在价格结构、估值质量、经营质量三个维度没有一个明显弱于 A；
2. B 至少一个维度明显更优；
3. A 没有 B 无法覆盖的明显差异化优势；
4. 不存在业务异质性、周期失真或数据冲突，需要公开研究才能判断。

只要互有胜负、不可比或不确定，就不得做同行支配淘汰。

`PEER_DOMINATED` 不能表达：

- 同行业公司太多，所以只留 1–2 只；
- 同风险簇所以提前压缩；
- 券商、资源品等共同受一个变量驱动，所以只研究少数代表；
- 为了降低 `deep_read_codes` 数量而选少数更优公司；
- 预计最终榜只需要一个行业席位，所以提前去重。

这些属于 coverage COMPLETE 后的 Risk Cluster Consolidation。

每个 `PEER_DOMINATED` entry 至少保留：

- `dominated_by`
- `price_structure_basis`
- `valuation_basis`
- `operating_basis`
- `differentiated_advantage_check`
- `uncertainty_check`

如果这些依据无法成立，不得标记 `PEER_DOMINATED`。

### 3.2 公司绝对质量

未被 `PEER_DOMINATED` 的公司只允许：

#### `CLEARLY_WEAK`

只有结构化事实显示多个独立方面明显偏弱，且没有清晰的确定性反向优势时才使用。单一 PE、ROE、利润增长、负现金流、行业状态或单个质量标签不得单独形成 `CLEARLY_WEAK`。

如果弱点可能由周期、会计口径、业务变化或缺失信息解释，应使用 `UNCERTAIN`。

#### `PASS_TO_DEEP_RESEARCH`

结构化事实已经显示继续研究具有明确价值。

#### `UNCERTAIN`

结构化数据不足以可靠解释公司，例如周期导致利润或估值可能失真、数据互相冲突、真实业务差异会改变数字含义、关键缺失信息可能改变结论。

拿不准时使用 `UNCERTAIN`，不要为了减少数量强行淘汰。

### 3.3 完整 Ledger

每只候选恰好有一个 `ledger_entry`：

- `code`
- `result`
- `reason_code`
- `reason`

`result` 只能是：

- `PEER_DOMINATED`
- `CLEARLY_WEAK`
- `PASS_TO_DEEP_RESEARCH`
- `UNCERTAIN`

代码集合只是逐公司 Ledger 的派生索引；集合与 entry 冲突即审计失败。

Structured Screening 禁止：

- 综合加权总分；
- 全市场 Top N；
- 每组机械 Top1 / Top2；
- 单指标一票淘汰；
- 为了压缩 Deep Research 数量调判断标准；
- 把 Risk Cluster / 行业相关性去重前移；
- 在完整 Ledger 冻结前引入公司级外部资料；
- 找到几只好公司后停止处理剩余候选。

研究层原则：

> **防漏优先；相关性去重留到完整 Deep Research 后的发布层。**

---

## 4. Deep Research

只有冻结后的 `PASS_TO_DEEP_RESEARCH` 和 `UNCERTAIN` 进入 Deep Research。

每家公司重点确认：

1. 真实主营、主要产品和业务；
2. `primary_profit_driver`：利润最主要由什么变量驱动；
3. `dominant_risk_factor`：最能同时解释上行与下行的主导外部或经营风险因子；
4. 未来 1–2 个季度盈利逻辑是否可验证；
5. 行业改善是否真实传导到公司；
6. 净利润、扣非、收入、毛利率、现金流、销量、价格、订单等是否互相支持；
7. 是否存在一次性收益；
8. 是否处于周期盈利高点，导致 PE 看似便宜；
9. 至少一条最可能推翻当前判断的反向证据。

### 4.1 Batch 只是执行容器

Stage B 可以为了降低工具调用和上下文负担，把 `deep_read_codes` 切成 execution batch；**Batch 只具有执行意义，不具有投资比较、配额、排名或淘汰意义。**

明确禁止：

- 每个 Batch 只保留固定数量公司；
- Batch 内 Top1 / Top2 / Top N；
- 因为本批已有若干优质公司，把其他满足条件公司降为 `waiting_for_entry` 或 `research_uncertain`；
- 把 Batch 相对排名作为公司状态依据；
- 把 Batch 当成同行组、Risk Cluster 或正式榜席位组。

同一 Batch 可以全部满足条件，也可以一个都不满足。申万三级行业、真实主营和共享主导变量只用于理解背景和复用行业证据，不产生 Batch 配额。

判断纪律：

> **公司状态由公司自己的证据决定；Batch 只决定一起处理谁，不决定留下谁。**

如果申万三级行业内实际业务不可比，应按真实主营、盈利驱动和利润来源理解公司，而不是强行用同一分析框架。

Deep Research 的目标是穷尽冻结后的 `deep_read_codes`，不是找到足够多可以出榜的公司。

### 4.2 统一状态机：先研究，再判断入场

Deep Research 对每家公司只做两层判断，不为四个终态分别建立四套规则。

#### A. Research Support Test

先回答：

> **这家公司的研究逻辑是否成立？**

结果只有三类：

- **成立**：主营、盈利驱动、盈利质量、主要风险与正常化盈利可以被足够证据解释，记为 `research_supported = true`；
- **被实质反证**：基本面明显恶化、盈利逻辑被否定、关键风险使研究目标失效 → `excluded`；
- **仍无法可靠判断**：存在会实质改变结论的具体事实缺口或冲突 → 进入 4.4 的 Uncertainty Resolution Pass；一次定向补查后仍无法解决才允许最终 `research_uncertain`。

价格暂时不好、买点不舒服、保守上行不足，都不属于 Research Support Test 的失败。

第一遍 Deep Research **不得把所有公司默认先放入 `research_uncertain` 再等待 Resolution Pass 证明**。Research Support Test 不要求“没有任何不确定性”，只要求现有证据已经足以形成可辩护、可证伪的研究判断：

- 如果现有证据足以解释主营、核心盈利驱动、盈利质量和主要风险，且不存在一个会实质改变研究结论的明确事实缺口或冲突，应直接记为 `research_supported = true`，随后进入 Unified Entry Evaluation；
- 只有能够明确指出一个**具体、尚未解决、且解决后可能实质改变研究结论**的事实缺口或冲突时，才允许进入 first-pass `research_uncertain`；
- “还可以继续查”“无法做到绝对确定”“资料不是完全穷尽”“估值存在正常区间”均不能单独构成 first-pass uncertain。

#### B. Unified Entry Evaluation

只有 `research_supported = true` 的公司进入统一 Entry Evaluation。`confirmed` 与 `waiting_for_entry` 必须使用**同一套公司级、可复算、可证伪的数值闭环**：

```text
正常化盈利区间
→ 正常化盈利中枢
× 可辩护的保守估值
→ conservative_fair_value / 最终安全区
→ conservative_upside
→ current_price 与 low_risk_buy_range / 最终安全区的关系
→ entry_ready
```

业务模式不适合 PE 时，可使用与业务匹配的 PB/ROE、现金流、资产价值或其他可辩护方法；不得强行统一为 PE。

统一规则：

1. 正常化盈利、估值依据与价格数据必须来自本轮锁定 runtime 或本轮 Deep Research 已取得并实际用于判断的事实，不得为结论倒推数字；
2. 强周期公司必须使用正常化盈利，禁止直接把高景气半年利润机械年化；
3. 估值允许合理区间，不要求单点精确值；
4. **单重保守**：默认使用“正常化盈利区间中枢 × 可辩护的保守估值”。不得机械使用“盈利区间下沿 × 估值区间下沿”作为正式 `conservative_fair_value` 或 entry blocker；这种双下沿结果只可作为 `stress_floor` 辅助观察；
5. 单独的 PE / PB / ROE、60 日低位、支撑距离或成交密集区不能证明 `entry_ready`，必须连接到价值、安全区和当前价；
6. 原则上 `conservative_upside >= 15%`；
7. 原则上当前价距离最终安全区约 5% 以内，或存在同等强度、可量化的下行保护依据。

Entry Evaluation 的核心关系可写为：

```text
conservative_upside = conservative_fair_value / current_price - 1
current_price 对比 low_risk_buy_range / 最终安全区 → downside_to_safety_zone
```

如果业务采用非 PE 方法，也必须得到同等级可复算的保守价值/安全区关系。

### 4.3 四个终态只做状态映射

统一按以下状态机：

```text
研究逻辑被实质反证
→ excluded

一次定向补查后，仍存在会实质改变研究结论的明确缺口/冲突
→ research_uncertain

research_supported = true
    ↓
Unified Entry Evaluation
    ├─ entry_ready = true  → confirmed
    └─ entry_ready = false → waiting_for_entry
```

#### `confirmed`

语义：

> `research_supported + entry_ready`

只有 Unified Entry Evaluation 整体支持当前低风险参与条件，才允许 `confirmed`。不得因为估值低、位置低、靠近支撑或同行更差而直接 confirmed。

#### `waiting_for_entry`

语义：

> `research_supported + not_entry_ready`

研究逻辑已经成立，但 Unified Entry Evaluation 中的当前价格、安全边际、保守上行空间或参与时机至少一项未满足。

每个 `waiting_for_entry` 只保留一个审计字段：

- `waiting_for_entry_reason`

该 reason 只需明确指出**统一 Entry Evaluation 中哪个条件未满足，并引用对应可复算关系**。例如：

- `conservative_fair_value` 对比 `current_price` 后，`conservative_upside < 15%`；
- 当前价高于 `low_risk_buy_range` / 最终安全区，并给出距离或溢价；
- 与业务匹配的正常化估值关系显示当前价格不足以覆盖公司自身风险。

禁止：

- 只列孤立现价、PE、PB、ROE；
- “安全边际不足”“还需观察”等没有计算关系的模板理由；
- 同 Batch、同行、Risk Cluster、榜单席位等相对比较；
- 用 `stress_floor` 直接替代正式 entry blocker。

如果研究逻辑已成立且统一 Entry Evaluation 可以完成，那么未达到 entry-ready 就应为 `waiting_for_entry`，不能因为“不够便宜”转成 `research_uncertain`。

`waiting_for_entry_reason` 必须满足机械审计：

```text
keys(waiting_for_entry_reason) == set(waiting_for_entry_codes)
len(waiting_for_entry_reason) == waiting_for_entry_count
```

同时：

- 每个 waiting code 恰好一条独立 reason；
- 禁止 `default`、`*`、`others` 或其他兜底键；
- 不得包含 confirmed / research_uncertain / excluded 的 code；
- reason 为空、泛化、相对比较或缺少可复算 blocker，均视为 waiting 审计失败。

waiting 审计未通过时，本轮不得标记 `PASSED` / `PUBLICATION_COMPLETE`。

`waiting` 只作为历史结果的 legacy alias；新运行统一输出 `waiting_for_entry`。

#### `research_uncertain`

只有研究证据本身仍不足时使用，不是无法证明 confirmed 时的默认出口。

允许的最终 uncertain 必须满足：经过一次定向 Resolution Pass 后，仍有一个**具体且会实质改变研究结论**的缺口或冲突。无法得到精确盈利预测、唯一目标价或单点合理价值，本身不构成 uncertain。

只要可以建立有事实依据的正常化盈利区间与匹配的估值区间，就必须完成 Unified Entry Evaluation。

#### `excluded`

研究逻辑被实质反证。不能仅因为当前价格不合适而 excluded。

### 4.4 Uncertainty Resolution Pass｜只消歧一次

只有第一遍 Research Support Test 已明确识别出一个会实质改变研究结论的具体缺口或冲突时，才记录 `uncertainty_reason` 并进入 first-pass `research_uncertain`。不得先默认 uncertain 再搜索理由。`uncertainty_reason` 只能属于：

- `DATA_GAP`：关键事实缺失、关键来源无法取得，或可靠来源冲突；
- `NORMALIZATION_GAP`：无法建立有事实依据的正常化盈利合理区间，或无法建立与其匹配的可辩护估值区间；
- `THESIS_CONFLICT`：支持与反向证据都足够强，无法判断研究逻辑成立还是被否定。

`NORMALIZATION_GAP` 不包括：无法得到精确单点、正常区间较宽、无法确定唯一目标价。

每个 uncertainty 必须回答：

1. 具体缺失或冲突的事实是什么；
2. 该事实解决后是否可能实质改变研究结论；
3. 是否已针对该缺口做过一次定向补查。

第一遍结束后，只针对这些公司执行一次 `Uncertainty Resolution Pass`：

- `DATA_GAP`：补查缺失公告、财报、公司披露或冲突事实；
- `NORMALIZATION_GAP`：补查周期位置、价差/价格、历史盈利区间、一次性收益和正常化依据，目标是建立合理区间；
- `THESIS_CONFLICT`：明确 strongest bull case 与 strongest bear case，并补查最可能改变判断的关键证据。

Resolution Pass 只允许**一次定向补充研究 + 一次重新判断**，不得无限追加搜索，也不得为了降低 uncertain 数量强行选边。

重新判断：

- 研究逻辑被实质反证 → `excluded`；
- 关键缺口仍未解决且确实可能改变研究结论 → `research_uncertain`；
- Research Support Test 已通过 → 必须进入 Unified Entry Evaluation，再映射为 `confirmed` 或 `waiting_for_entry`。

特别约束：

> **只要正常化盈利与估值的合理区间能够建立，就不能因为“不够精确”“保守价值不支持买入”而保留 research_uncertain；前者不构成缺口，后者属于 waiting_for_entry。**

强周期公司不得仅因“周期性强”保留 uncertain；必须先尝试建立正常化盈利区间。

正式状态仍只有四种，不增加第五种状态。`uncertainty_reason` 只是诊断字段。

可记录：

```text
first_pass_uncertain_count
final_research_uncertain_count
uncertainty_resolved_count
uncertainty_resolution_rate = uncertainty_resolved_count / first_pass_uncertain_count
```

这些指标只用于观察，不得设置目标比例、最低解决率或配额。

### 4.5 派生研究集合

必须派生：

```text
research_supported_codes = confirmed_codes ∪ waiting_for_entry_codes
research_supported_count = confirmed_count + waiting_for_entry_count
entry_ready_codes = confirmed_codes
entry_ready_count = confirmed_count
```

不得把 `waiting_for_entry` 表述为研究未确认、研究失败或被淘汰。

如果多家公司同时 `entry_ready`，它们必须全部先保持 `confirmed`，不论是否属于同一行业、同一 Batch 或未来同一 Risk Cluster。

---

## 5. 最终估值与低风险安全区

本节只补充 Unified Entry Evaluation 的估值纪律，不另建一套状态规则。

程序 Structure Filter 只表示当前价格结构值得研究，不是最终价值底，也不能直接复制成 `low_risk_buy_range`。

Deep Research 后尽量形成：

- `reasonable_price_range`
- `base_fair_value`
- `low_risk_buy_range`
- `conservative_upside`
- `downside_to_safety_zone`
- `hard_risk_boundary`（能可靠定义时）

最终安全区综合：

- 正常化盈利与业务匹配的保守估值；
- PE / PB 与 ROE、增长、现金流的匹配；
- 重要支撑与前期低点；
- 成交密集区；
- 真实主营、盈利驱动和盈利质量。

估值计算统一遵循 4.2 的 Unified Entry Evaluation，尤其是：

> **正式保守价值默认采用“正常化盈利区间中枢 × 可辩护的保守估值”；盈利下沿 × 估值下沿仅作为 stress floor，不直接作为 entry blocker。**

原则仍为：

- 当前价距离最终安全区约 5% 以内；
- 保守上行空间 `>= 15%`。

最近阻力只是短期压力，不直接等于全部上涨空间。

---

## 6. Risk Cluster Consolidation｜发布层去相关

这一阶段只在 Deep Research coverage = COMPLETE 且公司级估值完成后执行。

目标不是减少研究，而是避免正式榜把同一个共同风险因子重复展示成多个独立机会。

### 6.1 归簇依据

不能按申万行业代码机械归并。主要看 Deep Research 已确认的：

- `primary_profit_driver` 是否高度重合；
- 主要上涨催化是否由同一个关键变量驱动；
- 最重要的反向风险是否会由同一个关键变量同时触发。

如果核心因果关系高度重合，应归入同一 `risk_cluster`。

以下情况不得仅因同行业而强行合并：

- 主营和利润来源明显不同；
- 一个主要赚周期价格，一个主要赚加工费或服务费；
- 核心催化不同；
- 最主要下行风险不同；
- 公司特有事件足以形成独立投资逻辑。

不同行业公司如果高度依赖同一个主导变量，也可以归入同一风险簇。

### 6.2 Risk Cluster 只处理 entry-ready 机会

Risk Cluster Consolidation 只对 `entry_ready_codes`，即公司级 `confirmed` 机会做发布层去相关。

如果同一风险簇有多家公司都 `confirmed`：

1. 所有公司仍保持 `confirmed`；
2. 不得为了让一个风险簇只剩一个 confirmed 而提前把其他公司降为 `waiting_for_entry`；
3. 正式榜默认选择一个 `representative_code`；
4. 其余已确认公司保留为 `alternative_codes` / `alternative_candidates`。

组内代表优先级不新增综合评分，沿用：

> **最终安全边际 → 保守上行空间 → 基本面稳定性 → 参与时机**

如果没有明显优胜者，应说明代表仅用于榜单去重，并保留替代候选差异化优势。

同一行业多家公司若主导盈利驱动和主要风险暴露实质不同，可以分别占正式榜席位，并给出 `independence_rationale`。

每个正式机会至少保留：

- `risk_cluster`
- `dominant_risk_factor`
- `representative_code`
- `alternative_codes`
- `cluster_rationale`

正式榜排名对象是：

> **独立风险收益机会。**

---

## 7. 趋势与市场风险

趋势回答什么时候参与，不回答公司是否值得研究。

因此：

- `transition` / `bearish` 不得单独淘汰公司；
- 市场 `high risk` 不得缩小 Structured Screening 或 Deep Research 覆盖；
- 市场风险只能让最终估值与行动更保守、更倾向 `waiting_for_entry`；
- coverage COMPLETE 前不得生成正式榜；
- coverage COMPLETE 后正式机会集合可以自然减少甚至为空。

---

## 8. 最终状态与排序

Deep Research 后公司状态统一按 4.3 状态机：

- `confirmed` = `research_supported + entry_ready`；
- `waiting_for_entry` = `research_supported + not_entry_ready`，且 waiting reason 审计通过；
- `research_uncertain` = 一次 Resolution Pass 后仍存在会实质改变研究结论的明确缺口或冲突；
- `excluded` = 研究逻辑被实质反证。

Risk Cluster 不修改公司级状态，只改变正式榜如何表达高度相关的 `confirmed` 机会。

正式输出必须同时报告：

- `confirmed_count`
- `waiting_for_entry_count`
- `waiting_for_entry_reason`
- `research_uncertain_count`
- `excluded_count`
- `research_supported_count = confirmed + waiting_for_entry`
- `entry_ready_count = confirmed`

正式机会榜优先级：

> **最终安全边际 → 保守上行空间 → 基本面稳定性 → 参与时机**

正式机会榜不设目标数量，也不设固定数量上限。所有满足最终低风险条件、经 Risk Cluster Consolidation 后仍属于独立风险收益机会的结果都进入正式机会集合；数量由事实自然产生，可以为 0，也可以超过 10。

排名只表示机会优先级，不作为研究停止条件，也不以第 N 名截断。

---

## 9. 不变原则

> **程序负责事实和资格，模型负责关系和解释。**

> **Structured Screening 只使用锁定 GitHub runtime；Deep Research 才引入公司级外部公开资料。**

> **PEER_DOMINATED 只用于真正的公司级明确支配，不用于行业去重或风险簇压缩。**

> **研究层防漏，发布层去相关。**

> **Batch 只用于执行分包，不用于投资比较、配额或组内淘汰。**

> **公司状态只走一条链：Research Support Test → Unified Entry Evaluation → 四状态映射；confirmed 与 waiting 不得各自建立不同的估值规则。**

> **统一 Entry Evaluation 必须形成公司级可复算关系；孤立 PE、PB、ROE、低位或支撑不能单独证明 confirmed 或 waiting blocker。**

> **采用单重保守：正式 conservative_fair_value 默认用正常化盈利区间中枢 × 可辩护保守估值；盈利下沿 × 估值下沿仅作 stress floor，不直接作为 entry blocker。**

> **无法得到精确单点估值不得成为 research_uncertain 理由；只要合理区间可建立，就必须完成 Entry Evaluation。**

> **waiting_for_entry_reason 的键集合必须与 waiting_for_entry_codes 完全一致；禁止兜底理由、相对比较和不可复算 blocker。**

> **research_uncertain 必须有明确、可改变结论的 uncertainty_reason，并经过一次定向 Uncertainty Resolution Pass 后仍无法解决；第一遍不得默认把所有公司放入 uncertain，也不得把它当作无法证明 confirmed 时的默认出口。**

> **同一 Risk Cluster 可以有多家公司同时 confirmed；Risk Cluster 只能在之后选择代表，不得反向降级公司状态。**

> **任务完成的定义是冻结研究集合全部得到公司级研究结论，不是找到足够多可以出榜的公司。**

> **Deep Research coverage 未 COMPLETE 时，不生成正式独立机会榜。**

> **正式机会集合不设 Top N、目标数量或固定上限。**

> **不使用综合评分、Top N 或市场风险截断替代完整研究。**

> **结构硬筛是研究准入，不是最终价值底。**
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

### 4.2 公司研究结论与入场时机必须分开

这是 Deep Research 的核心语义边界。

模型必须先回答：

> **这家公司的研究逻辑是否成立？**

再回答：

> **当前价格是否已经进入低风险参与条件？**

不得把“研究是否成立”和“现在能不能买”混成一个相对排名。

现有四个终态严格定义为：

#### `confirmed`

同时满足：

1. 公司研究逻辑已有足够证据支持；
2. 正常化盈利、盈利质量和主要风险可以可靠解释；
3. 当前价格、最终安全边际、保守上行空间和参与时机已经满足本轮低风险参与条件。

语义：

> `research_supported + entry_ready`

#### `waiting_for_entry`

公司研究逻辑已有足够证据支持，但当前价格、安全边际、保守上行空间或参与时机尚未满足低风险入场条件。

语义：

> `research_supported + not_entry_ready`

`waiting_for_entry` 不是研究失败，也不是“同批已有更好的公司”。只要研究逻辑成立但当前不适合买入，就应使用 `waiting_for_entry`。

每个 `waiting_for_entry` 只增加一个可审计字段：

- `waiting_for_entry_reason`：为什么**当前不能成为 confirmed**。必须明确落在当前价格、最终安全边际、保守上行空间或参与时机中的一个或多个具体阻碍。

只有先证明 `research_supported = true`，才允许进入 `waiting_for_entry`。如果仍存在会实质改变研究结论的关键事实缺口、正常化盈利无法建立、或正反证据仍无法判定，则不得使用 `waiting_for_entry`，应进入 `research_uncertain`。

`waiting_for_entry_reason` 不得写成“仍需观察”“存在不确定性”“盈利持续性待确认”“周期位置看不清”“等待更多数据”等研究层模糊理由；这些说明研究结论尚未闭合，不属于买点问题。

`waiting_for_entry_reason` 还不得以任何相对比较作为状态依据，包括但不限于：

- “同 Batch 有更好的公司”；
- “同行有更优候选”；
- “同 Risk Cluster 已有代表候选”；
- “与已确认公司共享风险，因此不重复占位”；
- “结构略逊于代表候选”；
- “正式榜席位已被其他公司占用”。

如果公司凭自身证据已满足 `confirmed` 的公司级条件，必须先保持 `confirmed`；同行、Batch、Risk Cluster 或正式榜去重只能在之后决定是否作为 `representative_code` 或 `alternative_codes`，不得反向把公司降为 `waiting_for_entry`。

该字段必须随本轮公司状态写入执行记录，并满足机械审计：

```text
keys(waiting_for_entry_reason) == set(waiting_for_entry_codes)
len(waiting_for_entry_reason) == waiting_for_entry_count
```

同时：

- 每个 waiting code 必须恰好有一条独立 reason；
- 禁止 `default`、`*`、`others`、通用模板键或任何兜底理由；
- `waiting_for_entry_reason` 不得包含 confirmed / research_uncertain / excluded 的 code；
- reason 为空、泛化、引用相对排名/风险簇去重，均视为 waiting 审计失败。

没有通过上述集合一致性与理由合法性校验时，本轮不得把 execution probe 标记为 `PASSED` / `PUBLICATION_COMPLETE`。

`waiting` 只作为历史结果的 legacy alias；新运行统一输出 `waiting_for_entry`。

#### `research_uncertain`

研究证据本身不足、关键来源冲突、周期正常化无法可靠判断、真实业务或关键事实无法验证。

不能仅因为当前价格暂时不好而使用 `research_uncertain`；价格或时机不合适但研究逻辑成立，应使用 `waiting_for_entry`。

#### `excluded`

公司级研究已经出现足以否定投资逻辑的实质问题，例如基本面明显恶化、盈利逻辑被反证、正常化估值失去合理性或关键风险使其不再符合研究目标。

不能仅因为当前价格不合适而 `excluded`。

### 4.3 Uncertainty Resolution Pass｜不确定性必须被解释并只消歧一次

Stage B 第一遍研究中，如公司暂时落入 `research_uncertain`，该状态只能视为**待消歧候选**，不能立刻作为最终终态进入 coverage COMPLETE。

每个待消歧公司必须先记录一个 `uncertainty_reason`，且只能属于以下三类之一：

- `DATA_GAP`：关键事实缺失、关键来源无法取得，或不同可靠来源之间存在会改变结论的冲突；
- `NORMALIZATION_GAP`：正常化盈利、周期位置、一次性收益或高景气利润能否持续无法可靠判断；
- `THESIS_CONFLICT`：支持投资逻辑与反向证据都足够强，当前证据不足以可靠判断研究逻辑成立还是被否定。

判定 `research_uncertain` 前必须明确回答：

1. **具体缺失或冲突的事实是什么？**不得只写“信息不足”“存在不确定性”等泛化理由；
2. **这个事实如果得到解决，是否可能实质改变公司终态？**如果不会改变终态，不得以此作为 uncertain 理由；
3. **是否已经针对这个具体缺口做过一次定向补充研究？**

第一遍结束后，必须仅针对这些待消歧公司执行一次 `Uncertainty Resolution Pass`：

- `DATA_GAP`：只补查缺失的公告、财报、公司披露或冲突事实；
- `NORMALIZATION_GAP`：只补查周期位置、价差/价格、历史盈利区间、一次性收益和正常化利润依据；
- `THESIS_CONFLICT`：明确 strongest bull case 与 strongest bear case，并补查最可能改变判断的关键证据。

Resolution Pass 只允许**一次定向补充研究 + 一次重新判断**，不得无限追加搜索，也不得为了降低 uncertain 数量强行选边。

重新判断时：

- 研究逻辑成立且当前 entry-ready → `confirmed`；
- 研究逻辑成立但只是当前价格、安全边际、上行空间或时机不合适，并且能够给出逐股、合法、非相对比较的 `waiting_for_entry_reason` → `waiting_for_entry`；
- 研究逻辑被实质反证 → `excluded`；
- 只有具体缺口在一次定向补充研究后仍然无法解决，且该缺口确实可能改变研究结论 → 最终 `research_uncertain`。

从 first-pass `research_uncertain` 转为 `waiting_for_entry` 时，必须确认原始 uncertainty 已被新增证据解决；如果只能证明“目前没有明显坏消息”，但无法证明研究逻辑已成立，不得迁移到 `waiting_for_entry`。

特别约束：

> **价格不合适、买点不舒服、保守上行空间暂时不足，本身都不是 research_uncertain；只要研究逻辑已经成立，应归入 waiting_for_entry。**

对于强周期公司，不得仅以“周期性强”为由直接保留 uncertain。必须先尝试建立保守正常化盈利区间；只有连可辩护的正常化区间都无法建立时，才允许 `NORMALIZATION_GAP`。

正式状态仍只有四种，不增加第五种状态。`uncertainty_reason` 只是 `research_uncertain` 的诊断字段。

本轮可记录诊断指标：

```text
first_pass_uncertain_count
final_research_uncertain_count
uncertainty_resolved_count
uncertainty_resolution_rate = uncertainty_resolved_count / first_pass_uncertain_count
```

这些指标只用于观察 Deep Research 是否真正降低不确定性，**不得设置目标比例、最低解决率或配额，也不得据此强迫模型改变公司状态。**

### 4.4 派生研究集合

必须派生：

```text
research_supported_codes = confirmed_codes ∪ waiting_for_entry_codes
research_supported_count = confirmed_count + waiting_for_entry_count
entry_ready_codes = confirmed_codes
entry_ready_count = confirmed_count
```

必须明确区分：

- `research_supported_count`：有多少家公司研究逻辑成立；
- `entry_ready_count`：其中多少家公司当前就是低风险买点。

不得把 `waiting_for_entry` 表述为研究未确认、研究失败或被淘汰。

如果多家公司同时 `entry_ready`，它们必须全部先保留为 `confirmed`，不论是否属于同一行业、同一 Batch 或未来同一 Risk Cluster。

---

## 5. 最终估值与低风险安全区

程序 Structure Filter 只表示当前价格结构值得研究，不是最终价值底，也不能直接复制成 `low_risk_buy_range`。

Deep Research 后尽量形成：

- `reasonable_price_range`
- `base_fair_value`
- `low_risk_buy_range`
- `conservative_upside`
- `downside_to_safety_zone`
- `hard_risk_boundary`（能可靠定义时）

最终安全区综合：

- 正常化盈利对应的合理估值低位；
- PE / PB 与 ROE、增长、现金流的匹配；
- 重要支撑与前期低点；
- 成交密集区；
- 真实主营、盈利驱动和盈利质量。

强周期公司必须使用正常化盈利，禁止直接用高景气利润外推。

原则上优先：

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

Deep Research 后公司状态为：

- `confirmed`：研究成立且当前 entry-ready；
- `waiting_for_entry`：研究成立、具有逐股合法 `waiting_for_entry_reason`，但等待低风险入场；
- `research_uncertain`：一次 Uncertainty Resolution Pass 后仍存在会实质改变研究结论的明确证据缺口或冲突；
- `excluded`：研究逻辑被实质否定。

`waiting` 只作为历史结果的 legacy alias；新运行统一输出 `waiting_for_entry`。

Risk Cluster 不修改这些公司级状态，只改变正式榜如何表达相互高度相关的 `confirmed` 机会。

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

> **研究逻辑成立与当前是否可买必须分开；waiting_for_entry 属于 research_supported，且每只 waiting 必须有独立、具体、非相对比较的 waiting_for_entry_reason。**

> **waiting_for_entry_reason 的键集合必须与 waiting_for_entry_codes 完全一致；禁止 default 或任何兜底理由，禁止把 Risk Cluster / 同行相对优劣作为 waiting 原因。**

> **research_uncertain 必须有明确、可改变结论的 uncertainty_reason，并经过一次定向 Uncertainty Resolution Pass 后仍无法解决；不得把它当作拿不准时的默认安全出口。**

> **同一 Risk Cluster 可以有多家公司同时 confirmed；Risk Cluster 只能在之后选择代表，不得反向降级公司状态。**

> **任务完成的定义是冻结研究集合全部得到公司级研究结论，不是找到足够多可以出榜的公司。**

> **Deep Research coverage 未 COMPLETE 时，不生成正式独立机会榜。**

> **正式机会集合不设 Top N、目标数量或固定上限。**

> **不使用综合评分、Top N 或市场风险截断替代完整研究。**

> **结构硬筛是研究准入，不是最终价值底。**
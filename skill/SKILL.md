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

只有结构化事实显示**至少两个相互独立的方面明显偏弱**，且没有清晰的确定性反向优势时才使用。单一 PE、ROE、利润增长、负现金流、行业状态或单个质量标签不得单独形成 `CLEARLY_WEAK`。

如果弱点可能由周期、会计口径、业务变化或缺失信息解释，应使用 `UNCERTAIN`。

每个 `CLEARLY_WEAK` entry 必须额外保留：

- `weakness_1`：第一个独立且可由锁定结构化事实直接支持的明显弱点；
- `weakness_2`：第二个独立且可由锁定结构化事实直接支持的明显弱点；
- `counter_advantage_check`：是否存在足以抵消上述弱点的确定性反向优势，以及为什么不足以推翻 CLEARLY_WEAK；
- `uncertainty_check`：为什么这些弱点不依赖公司级外部研究、周期正常化或缺失信息才能解释。

如果无法同时写出两个独立弱点，或 `uncertainty_check` 仍存在实质疑问，不得使用 `CLEARLY_WEAK`，应进入 `UNCERTAIN`。

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

其中 `PEER_DOMINATED` 与 `CLEARLY_WEAK` 必须同时满足各自的额外审计字段要求；字段不完整时不得冻结 Ledger。

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

Stage B 的 execution batch 是确定性的：

```text
batch_size = 12 companies
order = frozen deep_read_codes 的既定顺序
```

按 frozen `deep_read_codes` 原始顺序依次切分，每批最多 12 家，最后一批可以少于 12 家。不得为了行业、真实业务、主导变量、候选质量或预期结论重新排序或重组 execution batch。

**Batch 只具有执行意义，不具有投资比较、配额、排名或淘汰意义。**

明确禁止：

- 每个 Batch 只保留固定数量公司；
- Batch 内 Top1 / Top2 / Top N；
- 因为本批已有若干优质公司，把其他满足条件公司降为 `waiting_for_entry` 或 `research_uncertain`；
- 把 Batch 相对排名作为公司状态依据；
- 把 Batch 当成同行组、Risk Cluster 或正式榜席位组。

同一 Batch 可以全部满足条件，也可以一个都不满足。申万三级行业、真实主营和共享主导变量只用于理解背景、选择分析框架和复用行业证据，不得改变 execution batch 边界，也不产生任何 Batch 配额。

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

正式公司终态只允许以下四个名称：

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

`waiting` 不再是正式状态名，不得在新运行的公司级结果或审计字段中使用。

#### `research_uncertain`

研究证据本身不足、关键来源冲突、周期正常化无法可靠判断、真实业务或关键事实无法验证。

不能仅因为当前价格暂时不好而使用 `research_uncertain`；价格或时机不合适但研究逻辑成立，应使用 `waiting_for_entry`。

#### `excluded`

公司级研究已经出现足以否定投资逻辑的实质问题，例如基本面明显恶化、盈利逻辑被反证、正常化估值失去合理性或关键风险使其不再符合研究目标。

不能仅因为当前价格不合适而 `excluded`。

### 4.3 派生研究集合

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
3. 正式榜选择且仅选择一个 `representative_code`；
4. 其余已确认公司保留为 `alternative_codes`。

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

### 6.3 发布层硬不变量

Risk Cluster Consolidation 完成后必须同时满足：

```text
formal_opportunity_count
== risk_cluster_count
== len(formal_representative_codes)
```

并且：

```text
confirmed_codes
= formal_representative_codes ∪ all_alternative_codes
```

同时要求：

- `formal_representative_codes` 与全部 `alternative_codes` 互斥；
- 每个 `confirmed` code 必须且只能属于一个 `risk_cluster`；
- 每个 risk cluster 必须且只能有一个 `representative_code`；
- 任何 `waiting_for_entry / research_uncertain / excluded` 都不得进入 Risk Cluster 正式机会集合。

任一不变量不成立，发布层验证失败，不得把不一致结果作为正式榜输出。

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

Deep Research 后公司正式状态为：

- `confirmed`：研究成立且当前 entry-ready；
- `waiting_for_entry`：研究成立但等待低风险入场；
- `research_uncertain`：研究证据不足或冲突；
- `excluded`：研究逻辑被实质否定。

Risk Cluster 不修改这些公司级状态，只改变正式榜如何表达相互高度相关的 `confirmed` 机会。

正式输出必须同时报告：

- `confirmed_count`
- `waiting_for_entry_count`
- `research_uncertain_count`
- `excluded_count`
- `research_supported_count = confirmed_count + waiting_for_entry_count`
- `entry_ready_count = confirmed_count`

正式机会榜优先级：

> **最终安全边际 → 保守上行空间 → 基本面稳定性 → 参与时机**

正式机会榜不设目标数量，也不设固定数量上限。所有满足最终低风险条件、经 Risk Cluster Consolidation 后仍属于独立风险收益机会的结果都进入正式机会集合；数量由事实自然产生，可以为 0，也可以超过 10。

排名只表示机会优先级，不作为研究停止条件，也不以第 N 名截断。

---

## 9. 不变原则

> **程序负责事实和资格，模型负责关系和解释。**

> **Structured Screening 只使用锁定 GitHub runtime；Deep Research 才引入公司级外部公开资料。**

> **PEER_DOMINATED 只用于真正的公司级明确支配，不用于行业去重或风险簇压缩。**

> **CLEARLY_WEAK 必须有两个独立弱点，并明确说明为何无需外部研究即可确认；拿不准就进入 UNCERTAIN。**

> **研究层防漏，发布层去相关。**

> **Stage B 固定按 frozen deep_read_codes 顺序每 12 家分批；Batch 只用于执行分包，不用于投资比较、配额或组内淘汰。**

> **研究逻辑成立与当前是否可买必须分开；waiting_for_entry 属于 research_supported。**

> **同一 Risk Cluster 可以有多家公司同时 confirmed；Risk Cluster 只能在之后选择代表，不得反向降级公司状态。**

> **一个 Risk Cluster 只能对应一个 formal opportunity；其他 confirmed 必须作为 alternatives 保留。**

> **任务完成的定义是冻结研究集合全部得到公司级研究结论，不是找到足够多可以出榜的公司。**

> **Deep Research coverage 未 COMPLETE 时，不生成正式独立机会榜。**

> **正式机会集合不设 Top N、目标数量或固定上限。**

> **不使用综合评分、Top N 或市场风险截断替代完整研究。**

> **结构硬筛是研究准入，不是最终价值底。**
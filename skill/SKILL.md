# A股低风险买点榜｜模型判断规则

## 1. 目标

寻找：

> **基本面没有明显恶化，当前价格经过价值与价格结构双重验证后具备安全边际，向下剩余空间有限，而未来 1–2 个季度保守上行空间充足的 A 股公司。**

核心原则：

> **先看还能跌多少，再看能涨多少。**

本文件只定义模型判断。确定性筛选、结构硬规则、数据校验、文件读取、阶段交接和覆盖审计，以程序输出、`meta.json` 和 `RUNTIME_READ_PROTOCOL.md` 为准。

---

## 2. 职责边界

程序已经确定：

- Eligibility Filter 与 Structure Filter；
- 价格位置、支撑、成交密集区和 `structure_tier`；
- 申万三级行业分组；
- PE / PB / ROE、收入、利润、扣非、现金流、毛利率等结构化事实；
- 行业状态、行业聚合事实和可直接计算的质量标签；
- Stage A 可直接使用的程序化质量事实，包括非核心 EPS 差异代理、经营现金流匹配、行业→公司传导关系。

这些程序化事实只表达确定性数据关系，不直接代表业务原因，也不是单指标硬淘汰规则。模型不得重新计算或推翻程序硬筛。

所有公司与行业 YoY 字段统一使用 `percentage_points`，例如 `12.4` 表示 `12.4%`。

模型负责四件事：

1. **Structured Screening / Model Prescreen**：只使用锁定 GitHub runtime 的结构化事实，判断同行明确支配和公司绝对质量；
2. **Stage B Research Worthiness Gate**：对 Frozen Ledger 的 `deep_read_codes` 全量做轻量判断，先回答“核心盈利是否可信”和“当前是否可能存在低风险安全边际”，只把真正值得投入完整研究预算的公司送入 Deep Research；
3. **Deep Research**：只研究 Gate 后派生的 `deep_research_required_codes`，引入公开资料确认真实业务、盈利驱动、周期、盈利质量、估值和最终安全边际；
4. **Risk Cluster Consolidation**：只有 Stage B coverage 完整闭合后，才把高度依赖同一主导风险因子的入场机会归并为独立风险收益机会。

Gate 是研究预算分配，不是 Top N、同行配额或风险簇去重。

---

## 3. Structured Screening / Model Prescreen

这一层只使用程序准备好的 `screening_groups` 及同一锁定 runtime 下允许的仓库结构化事实。

**Repository-only** 表示：在完整 Ledger FROZEN 并通过 Hard Gate 前，不得搜索或读取公司官网、公告正文、新闻、研报、搜索引擎结果、行业网站等公司级外部公开资料。

### 3.1 同行明确支配

在每个申万三级行业组内，单只组不存在同行支配，直接进入公司绝对质量判断。

多只组只比较：

- **价格结构**：位置、支撑距离与触碰、成交密集区距离与占比、阻力和风险参考；
- **估值质量**：PE-TTM、动态 PE、PB 与 ROE、增长、盈利质量是否匹配；
- **经营质量**：收入、净利润、扣非、经营现金流、毛利率，以及程序化质量事实。

候选 A 只有在存在同组候选 B 且同时满足时，才允许标记 `PEER_DOMINATED`：

1. B 在价格结构、估值质量、经营质量三个维度没有一个明显弱于 A；
2. B 至少一个维度明显更优；
3. A 没有 B 无法覆盖的明显差异化优势；
4. 不存在业务异质性、周期失真或数据冲突，需要公开研究才能判断。

只要互有胜负、不可比或不确定，就不得做同行支配淘汰。

`PEER_DOMINATED` 不能表达：同行公司太多、同风险簇提前压缩、只研究代表公司、为了降低后续研究数量而选 Top N、或预留正式榜席位。

每个 `PEER_DOMINATED` entry 至少保留：

- `dominated_by`
- `price_structure_basis`
- `valuation_basis`
- `operating_basis`
- `differentiated_advantage_check`
- `uncertainty_check`

### 3.2 公司绝对质量

程序质量事实用于减少必须留到公开研究才能发现的基础矛盾，但使用纪律是：

- 单一质量事实不得一票淘汰；
- 多个彼此独立的负向事实，可以与价格结构、估值和经营趋势共同支持 `CLEARLY_WEAK`；
- 程序事实已经闭合时，不得仅因为“还想联网确认”而使用 `UNCERTAIN`；
- 若负向事实可能由周期、会计口径、业务结构变化解释，且解释会实质改变结论，使用 `UNCERTAIN`。

未被 `PEER_DOMINATED` 的公司只允许：

#### `CLEARLY_WEAK`

结构化事实显示多个独立方面明显偏弱，且没有清晰确定性反向优势。单一 PE、ROE、利润增长、负现金流、行业状态或单个质量标签不得单独形成 `CLEARLY_WEAK`。

#### `PASS_TO_DEEP_RESEARCH`

结构化事实显示继续进入 Stage B 具有明确价值。

#### `UNCERTAIN`

结构化数据不足以可靠解释公司，例如周期导致利润或估值可能失真、程序事实互相冲突、真实业务差异会改变数字含义、关键缺失信息可能改变结论。

拿不准时不能为了压缩数量强行淘汰；但程序事实已经足够时，也不得把 `UNCERTAIN` 当默认出口。

### 3.3 完整 Ledger

每只候选恰好一个 `ledger_entry`：

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

Structured Screening 禁止：综合评分、全市场 Top N、每组机械 Top1/Top2、单指标一票淘汰、为了压缩后续研究数量调整标准、把 Risk Cluster 前移、FROZEN 前引入公司级外部资料、找到几只好公司后提前停止。

> **Stage A 防漏优先；Stage B Gate 再做研究预算分配；Risk Cluster 留到完整研究后的发布层。**

---

## 4. Stage B｜先轻量 Gate，再重点 Deep Research

Frozen Ledger 中的 `PASS_TO_DEEP_RESEARCH + UNCERTAIN` 形成 `deep_read_codes`。从本版开始：

> **`deep_read_codes` 是 Stage B 候选全集，不再自动等于必须做完整 Deep Research 的集合。**

Stage B 先对 `deep_read_codes` 全量执行 4.0 Research Worthiness Gate；只有 Gate 后派生的 `deep_research_required_codes` 才进入完整 Deep Research。

### 4.0 Research Worthiness Gate｜只回答两个问题

Gate 不判断“是不是最好的公司”，只回答：

> **Q1：正常化后的核心盈利是否可信、可持续？**

> **Q2：如果核心盈利可信，以当前价格粗看，是否仍有可能形成低风险安全边际？**

默认原则：

> **只有明确 No 才将该公司标记为 Gate-filtered；信息不足、边界或可解释，一律继续进入后续流程。**

Gate 不允许综合评分、Top N、行业配额或相对排名。

#### A. Q1｜结构化盈利可信度硬门

只使用锁定 runtime。满足任一条件才允许 `gate_filtered_q1`：

```text
1. net_profit_yoy < 0 AND deduct_basic_eps_yoy < 0
2. net_profit_yoy >= 20 AND deduct_basic_eps_yoy <= -10
3. quality_flag.profit_growth_cashflow_negative == true
   AND (deduct_basic_eps_yoy is null OR deduct_basic_eps_yoy <= 0)
4. net_profit_yoy >= 50
   AND deduct_basic_eps_yoy is not null
   AND deduct_basic_eps_yoy <= 5
```

这四条只用于 Stage B Gate，不反向修改 Stage A Ledger。

#### B. Q2｜结构化安全边际粗筛

只有 Q1 未明确 No 才进入 Q2。

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

Q2 只是判断“明显不值得立即花完整研究预算”，不是正式目标价计算。

#### C. Q2-lite｜只做一次极小的盈利归一化

对未被 Q1/Q2 标记为 Gate-filtered、但满足以下任一触发条件的公司，允许做 **1–2 次公司级定向查询**：

```text
valuation_borderline:
max_positive(pe_ttm, pe_dynamic) >= 18
AND roe < 8
AND deduct_basic_eps_yoy < 20

headline_anomaly:
net_profit_yoy >= 50
AND (
  deduct_basic_eps_yoy is null
  OR net_profit_yoy - deduct_basic_eps_yoy >= 30
  OR net_profit_yoy - revenue_yoy >= 40
)
```

Q2-lite 只允许确认：

- 最新报告期归母净利润；
- 扣非/经常性归母净利润；
- 利润高速增长的公司披露原因；
- 是否存在重大一次性收益；
- 是否存在主导利润的联营/投资收益。

Q2-lite **禁止**：完整产业链研究、完整行业景气研究、催化剂地图、竞争格局长篇研究、正式目标价构造。

可计算：

```text
normalized_dynamic_pe
= pe_dynamic × 当期归母净利润 / 当期经常性归母净利润

normalized_pe_lite
= max_positive(pe_ttm, normalized_dynamic_pe)
```

只有高置信度情况才允许 `gate_filtered_q2_lite`：

1. 重大一次性/非经常性收益占当期归母净利润约 30% 或以上，去除后表面低估值明显失真，且不再能合理支持低风险安全边际；或
2. 对非金融经营型公司，公司披露利润增长主要来自联营/投资收益，且该收益已成为当期利润的主导来源，导致主营盈利驱动与表面利润增长明显不一致。

只要证据不足以形成上述明确结论，就不得 Gate 掉，继续完整 Deep Research。

#### D. Gate 输出与研究优先级

Gate 全量处理完 `deep_read_codes` 后，派生互斥集合：

```text
gate_filtered_q1_codes
gate_filtered_q2_codes
gate_filtered_q2_lite_codes
deep_research_required_codes
```

满足：

```text
deep_read_codes
= gate_filtered_q1_codes
∪ gate_filtered_q2_codes
∪ gate_filtered_q2_lite_codes
∪ deep_research_required_codes
```

Gate-filtered 公司不伪装成完成了完整 Deep Research 的 `excluded` / `waiting_for_entry`；它们保留：

- `gate_disposition`
- `gate_filter_reason`
- `gate_evidence`

只对 `deep_research_required_codes` 使用完整 Deep Research 四终态。

为了在同一次 invocation 内优先把最可能产生正式机会的公司研究完，可以对 `deep_research_required_codes` 做研究优先级排序：

```text
LOW_PRIORITY candidate only when:
normalized_pe_lite is available
AND normalized_pe_lite > 20
AND roe < 8
AND recurring_profit_growth < 20
```

其余为 `HIGH_PRIORITY`。缺失 Q2-lite 归一化证据时默认 `HIGH_PRIORITY`，防止误杀。

**LOW_PRIORITY 只是执行顺序，不是淘汰。** 本次 invocation 必须在 HIGH 完成后继续研究 LOW，直到全部 `deep_research_required_codes` 闭合或发生真实硬失败。

### 4.1 Batch 只是执行容器

Deep Research 可以为了降低工具调用和上下文负担分 batch；Batch 只具有执行意义，不具有投资比较、配额、排名或淘汰意义。

明确禁止：每批固定保留数量、Batch 内 Top N、因为本批已有若干优质公司就降低其他公司状态、把 Batch 当同行组/Risk Cluster/榜单席位组。

同一 Batch 可以全部满足条件，也可以一个都不满足。

> **公司状态由公司自己的证据决定；Batch 只决定一起处理谁。**

Deep Research 的目标是穷尽 `deep_research_required_codes`，不是找到足够多可以出榜的公司。

### 4.2 完整 Deep Research｜Research Support Test + Unified Entry Evaluation

对每个 `deep_research_required_code` 重点确认：

1. 真实主营、主要产品和业务；
2. `primary_profit_driver`；
3. `dominant_risk_factor`；
4. 未来 1–2 个季度盈利逻辑是否可验证；
5. 当行业→公司传导 `failed/mixed` 或存在关键冲突时解释原因；
6. 当现金流、扣非、收入、毛利率明显不匹配时确认销量、价格、订单、会计口径等能否解释；
7. 当一次性收益代理重大、缺失或冲突时确认真实一次性收益；
8. 是否处于周期盈利高点导致 PE 看似便宜；
9. 至少一条最可能推翻当前判断的反向证据。

#### A. Research Support Test

先回答：

> **这家公司的研究逻辑是否成立？**

- **成立**：主营、盈利驱动、盈利质量、主要风险与正常化盈利可被足够证据解释 → `research_supported = true`；
- **被实质反证**：基本面明显恶化、盈利逻辑被否定、关键风险使研究目标失效 → `excluded`；
- **仍无法可靠判断**：存在会实质改变结论的具体事实缺口或冲突 → 进入 4.4 Uncertainty Resolution Pass。

价格暂时不好、买点不舒服、保守上行不足，不属于 Research Support Test 失败。

不得把所有公司默认放入 `research_uncertain`。只有一个具体、尚未解决且可能实质改变研究结论的事实缺口，才允许 first-pass uncertain。

#### B. Unified Entry Evaluation

只有 `research_supported = true` 的公司进入统一 Entry Evaluation：

```text
正常化盈利区间
→ 正常化盈利中枢
× 可辩护的保守估值
→ conservative_fair_value / 最终安全区
→ conservative_upside
→ current_price 与 low_risk_buy_range / 最终安全区的关系
→ entry_ready
```

业务模式不适合 PE 时，可以使用与业务匹配的 PB/ROE、现金流、资产价值或其他可辩护方法。

统一规则：

1. 正常化盈利、估值依据与价格数据必须来自本轮锁定 runtime 或本轮实际取得并用于判断的研究事实；
2. 强周期公司必须使用正常化盈利，禁止把高景气半年利润机械年化；
3. 估值允许合理区间，不要求单点精确值；
4. 默认采用“正常化盈利区间中枢 × 可辩护的保守估值”；盈利下沿 × 估值下沿只作为 `stress_floor`；
5. 单独 PE/PB/ROE、60 日低位、支撑距离或成交密集区不能证明 `entry_ready`；
6. 原则上 `conservative_upside >= 15%`；
7. 原则上当前价距离最终安全区约 5% 以内，或有同等强度、可量化的下行保护依据。

### 4.3 四个 Deep Research 终态

```text
研究逻辑被实质反证
→ excluded

一次定向补查后仍存在实质缺口/冲突
→ research_uncertain

research_supported = true
    ↓
Unified Entry Evaluation
    ├─ entry_ready = true  → confirmed
    └─ entry_ready = false → waiting_for_entry
```

#### `confirmed`

`research_supported + entry_ready`。

#### `waiting_for_entry`

`research_supported + not_entry_ready`。

每个 `waiting_for_entry` 必须有唯一：

- `waiting_for_entry_reason`

reason 必须明确指出 Unified Entry Evaluation 中哪个条件未满足，并引用可复算关系，例如 `conservative_upside < 15%`、当前价高于低风险安全区多少、或正常化估值不足以覆盖公司自身风险。

禁止孤立 PE/PB/ROE、模板化“安全边际不足”、Batch/同行/Risk Cluster 相对比较、或用 stress floor 直接替代 entry blocker。

机械审计：

```text
keys(waiting_for_entry_reason) == set(waiting_for_entry_codes)
len(waiting_for_entry_reason) == waiting_for_entry_count
```

#### `research_uncertain`

只有一次定向 Resolution Pass 后仍存在会实质改变研究结论的具体缺口/冲突才使用。无法得到精确盈利预测、唯一目标价或单点合理价值，本身不构成 uncertain。

#### `excluded`

研究逻辑被实质反证。不能仅因为当前价格不合适而 excluded。

### 4.4 Uncertainty Resolution Pass｜只消歧一次

`uncertainty_reason` 只能属于：

- `DATA_GAP`
- `NORMALIZATION_GAP`
- `THESIS_CONFLICT`

每个 uncertainty 必须回答：具体缺什么/冲突什么；解决后是否可能实质改变研究结论；是否已经针对它做过一次定向补查。

Resolution Pass 只允许**一次定向补充研究 + 一次重新判断**，不得无限追加搜索。

重新判断：

- 研究逻辑被实质反证 → `excluded`；
- 关键缺口仍未解决且确实可能改变研究结论 → `research_uncertain`；
- Research Support Test 已通过 → 必须进入 Unified Entry Evaluation，再映射为 `confirmed` / `waiting_for_entry`。

只要正常化盈利与估值合理区间能够建立，就不能因为“不够精确”或“保守价值不支持买入”保留 uncertain；后者属于 waiting。

### 4.5 派生研究集合

完整 Deep Research 公司中必须派生：

```text
research_supported_codes = confirmed_codes ∪ waiting_for_entry_codes
research_supported_count = confirmed_count + waiting_for_entry_count
entry_ready_codes = confirmed_codes
entry_ready_count = confirmed_count
```

Gate-filtered 公司不计入这些完整 Deep Research 状态集合。

如果多家公司同时 `entry_ready`，必须全部先保持 `confirmed`，不论是否同一行业、Batch 或未来同一 Risk Cluster。

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

最终安全区综合正常化盈利与业务匹配的保守估值、PE/PB 与 ROE/增长/现金流的匹配、重要支撑与前期低点、成交密集区、真实主营/盈利驱动/盈利质量。

正式保守价值默认：

> **正常化盈利区间中枢 × 可辩护保守估值。**

盈利下沿 × 估值下沿只作为 stress floor，不直接作为 entry blocker。

原则仍为：

- 当前价距离最终安全区约 5% 以内；
- 保守上行空间 `>= 15%`。

最近阻力只是短期压力，不直接等于全部上涨空间。

---

## 6. Risk Cluster Consolidation｜发布层去相关

只有：

```text
stage_b_coverage = COMPLETE
AND deep_research_coverage = COMPLETE
```

且公司级估值完成后，才执行 Risk Cluster。

归簇主要看：

- `primary_profit_driver` 是否高度重合；
- 上涨催化是否由同一个关键变量驱动；
- 最重要反向风险是否会由同一变量同时触发。

不得按申万行业代码机械归并。同行业主营/利润来源/催化/下行风险不同，可以形成独立机会；不同行业若高度依赖同一变量也可以归为同一风险簇。

Risk Cluster 只处理 `entry_ready_codes`。同一风险簇多家公司都 `confirmed` 时：

1. 公司级状态全部保持 `confirmed`；
2. 正式榜默认选一个 `representative_code`；
3. 其余保留为 `alternative_codes` / `alternative_candidates`。

代表优先级：

> **最终安全边际 → 保守上行空间 → 基本面稳定性 → 参与时机**

正式榜排名对象是独立风险收益机会。

---

## 7. 趋势与市场风险

趋势回答什么时候参与，不回答公司是否值得研究。

因此：

- `transition` / `bearish` 不得单独淘汰公司；
- 市场 `high risk` 不得修改 Stage A 候选全集，也不得绕过 Stage B Gate 的固定规则；
- 市场风险可以让最终估值与行动更保守、更倾向 `waiting_for_entry`；
- Stage B coverage COMPLETE 前不得生成正式榜。

---

## 8. 最终状态与输出

正式输出必须同时区分：

### Gate 层

- `stage_b_candidate_count`
- `gate_filtered_q1_count`
- `gate_filtered_q2_count`
- `gate_filtered_q2_lite_count`
- `deep_research_required_count`
- `deep_research_high_priority_count`
- `deep_research_low_priority_count`

### 完整 Deep Research 层

- `confirmed_count`
- `waiting_for_entry_count`
- `waiting_for_entry_reason`
- `research_uncertain_count`
- `excluded_count`
- `research_supported_count = confirmed + waiting_for_entry`
- `entry_ready_count = confirmed`

Gate-filtered 不是完整 Deep Research 四终态，不得混入上述四状态统计。

正式机会榜优先级：

> **最终安全边际 → 保守上行空间 → 基本面稳定性 → 参与时机**

正式机会榜不设目标数量或固定上限。所有满足最终低风险条件、经 Risk Cluster Consolidation 后仍属于独立风险收益机会的结果都进入正式机会集合；数量可以为 0，也可以超过 10。

---

## 9. 不变原则

> **程序负责事实和资格，模型负责关系和解释。**

> **Stage A 只使用锁定 GitHub runtime；Frozen Ledger 通过后，Stage B Gate 才允许极少量定向公开查询；完整公司研究只属于 Deep Research。**

> **Stage B Gate 只回答两个问题：核心盈利是否可信、当前是否可能存在低风险安全边际。只有明确 No 才将该公司标记为 Gate-filtered，否则继续。**

> **Q2-lite 只做盈利归一化，不扩张成完整公司研究。**

> **Gate-filtered 公司不伪装成完整 Deep Research 的 excluded / waiting；完整四终态只属于 `deep_research_required_codes`。**

> **研究优先级只改变执行顺序，不改变研究全集；LOW_PRIORITY 仍必须在同一次 invocation 内完成。**

> **PEER_DOMINATED 只用于真正的公司级明确支配，不用于行业去重或风险簇压缩。**

> **Batch 只用于执行分包，不用于投资比较、配额或组内淘汰。**

> **完整 Deep Research 公司状态只走一条链：Research Support Test → Unified Entry Evaluation → 四状态映射。**

> **采用单重保守：正式 conservative_fair_value 默认用正常化盈利区间中枢 × 可辩护保守估值；双下沿仅作 stress floor。**

> **research_uncertain 必须有明确、可改变结论的 uncertainty_reason，并经过一次定向 Resolution Pass 后仍无法解决。**

> **同一 Risk Cluster 可以有多家公司同时 confirmed；Risk Cluster 只能在之后选择代表。**

> **任务完成的定义是：Stage B 候选全集全部经过 Gate，且所有 `deep_research_required_codes` 在本次 invocation 内完成完整研究，不是找到足够多可以出榜的公司。**

> **Stage B coverage 或 Deep Research coverage 未 COMPLETE 时，不生成正式独立机会榜。**

> **正式机会集合不设 Top N、目标数量或固定上限。**

> **结构硬筛是研究准入，不是最终价值底。**
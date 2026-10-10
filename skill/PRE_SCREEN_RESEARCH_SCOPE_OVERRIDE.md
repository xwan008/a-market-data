# A股趋势买点榜｜公司预筛与深度研究范围

## 1. 职责边界

本文件只定义：

```text
Frozen Working Set
→ Company Hard Filter
→ Lightweight Peer Pre-screen
→ 所有hard-eligible轻量趋势与机会评分
→ 每三级行业前置动态Top5／并列第6
→ 只对入选者深度业务核查及有限候补
→ 每主题动态买点Top5
```

本文件不负责：
- 展开行业 Universe；
- 读取 materialized industry view；
- 读取任何原始 company_industry_index / shard；
- 构造 working set。

这些由 `TREND_BUY_CANONICAL.md` 在 Freeze 前完成。

---

## 2. 输入

唯一公司事实输入：

`frozen working_set[industry_code]`

要求 working set 已通过 Freeze Gate：

```text
working_set_company_count == universe_company_count
post_freeze_shard_read_count == 0
post_freeze_materialized_read_count == 0
```

预筛阶段使用本轮冻结工作集计算，确保每家公司仅使用已审计的物化事实。

---

## 3. 公司级硬过滤

只允许以下公司级硬条件：

- ST；
- 价格缺失、非数值或 <= 0；
- 关键估值、财务或趋势结构数据缺失；
- 营收同比 < -20% 且净利润同比 < -50%；
- 其他已在正式规则中明确的数据完整性硬条件。

禁止使用三级行业的 trend / strength / breadth / confidence / buyability 做准入或排序。

硬过滤发生在 frozen working set 内，不改变原 Universe 审计。

---

## 4. 轻量同业预筛

**目标：** 对全量合格公司轻量计算基本面+买点机会，先动态选每三级行业Top5，再对有限入选者做深度业务研究；不再将「PE 越低越好」「60 日股价位置越低越好」视作独立优势。改为寻找**增长与估值匹配、盈利质量良好、趋势结构健康**的公司，避免低增长价值陷阱和盲目追逐高估值成长故事。仍只消费本轮已 Freeze 的 working set，禁止补读 shard/index/materialized、另行 Web 查询或引入未经验证的未来盈利预测。

### 4.1 输入及同业分位

沿用原有公司事实定义：
- `core_profit_yoy`：优先 `deduct_basic_eps_yoy`，缺失回退 `net_profit_yoy`；
- `non_core_eps_share_pct`：basic_eps、deduct_basic_eps 均有效时，`abs(basic_eps-deduct_basic_eps)/max(abs(basic_eps),0.01)*100`；
- `cashflow_positive`：`operating_cashflow_per_share > 0`；
- `valuation_metric`：优先正 `pe_ttm`，其次正 `pe_dynamic`，再次正 `pb`；**负/零 PE 不算极低估值**；
- `position_pct`：60 日位置，仅用于识别趋势与潜在过热，不再直接按「越低越好」加分；
- 已有 `current_price`、MA20、MA60、`trend_state`、`break_state` 和 60 日结构/成交数据，用于趋势健康度。

所有同业分位只在**相同三级行业 hard-eligible 公司**中计算。数值由小到大赋 0–1 百分位，重复值取平均名次；某指标只有一个有效样本时该指标分位取 0.5。非关键局部数据缺失采用以下中性回退，不伪造零增长或廉价估值；原第3节的关键数据硬过滤依旧生效，不增设硬过滤。

```text
revenue_growth_pct     = percentile(revenue_yoy, ascending)
core_profit_growth_pct = percentile(core_profit_yoy, ascending)

transmission_proxy =
  0.5*revenue_growth_pct
  + 0.5*core_profit_growth_pct
```

若可得事实显示利润同比受异常低基数、扭亏或一次性收益扭曲，且收入、扣非或经营现金流无法印证增长，则应记录「增长可靠性待核验」，将**受扭曲的增长分位**在估值匹配计算中按中性 0.5 处理，而不是用异常同比为高 PE 辩护。不因此提前否定商业传导、变更 hard filter 或创造前瞻预测。

### 4.2 盈利质量：保持原算法和 25% 权重

```text
cashflow_score = 1 if OCF/share > 0 else 0

one_off_score =
  1.0 if non_core_eps_share_pct < 20%
  0.5 if unavailable
  0.0 if >= 20%

quality = 0.5*cashflow_score + 0.5*one_off_score
```

### 4.3 估值匹配：替换低倍数单边奖励，权重仍为 20%

**正 PE 可比较时：** 仅按相同 PE 口径分组求 `pe_expensiveness_pct`（TTM 对 TTM、dynamic 对 dynamic；不混排 PE/PB）；倍数越高表示昂贵分位越高。同一行业、同口径至少三个有效可比样本才使用分位，否则昂贵分位取 0.5。增长分位与估值昂贵程度一同考察：

```text
growth_for_valuation_pct =
  transmission_proxy
  （受异常基数/一次性收益影响、且未被印证的增长部分按 0.5 中性处理）

valuation_attractiveness =
  clamp(0.5 + 0.5*(growth_for_valuation_pct - pe_expensiveness_pct), 0, 1)
```

**PE 无效而使用 PB 时：** 只在行业内有效 PB/ROE 可比样本均不少于三个时，将上述公式中 `growth_for_valuation_pct` 改为 `roe_strength_pct`，将 `pe_expensiveness_pct` 改为 `pb_expensiveness_pct`，考察 PB 与 ROE 匹配程度；否则 `valuation_attractiveness = 0.5`。负 PE、极低 PB 或异常一次性利润不应自动取得高分；缺少可比数据也不得擅自给高分。

这里的匹配评分只是**研究资源的同业排序代理**，不是真正的 PEG、预测盈利或合理价值计算：低 PE 但低增长不会单边受奖励，高 PE 且高质量增长也不会天然被排除。

### 4.4 趋势健康度：权重为 10%

使用 `trend_health_score`，只取已验证的价格与技术结构事实。依优先级执行：

```text
if already confirmed structure break / invalidation:
  trend_health_score = 0.00
else if current_price >= MA20 >= MA60:
  trend_health_score = 1.00
else if current_price >= MA60:
  trend_health_score = 0.75
else if current_price >= MA20:
  trend_health_score = 0.50
else if valid MA20, MA60 and current_price < both:
  trend_health_score = 0.25
else:
  trend_health_score = 0.50  # 局部缺失中性，仍服从原硬过滤
```

若 60 日位置较高（将 0–100 或 0–1 的 `position_pct` 统一规范到 0–1，例：>=0.90），**不得仅因为创新高扣分**。仅在股价偏离 MA20 的程度位于同三级行业最高四分位，且已有成交量/结构事实不能支持有效突破时，才将健康度上限设为 0.70，提示短期过热。若已有可信放量突破和结构支撑，不机械压分；证据缺失时不臆测过热。技术强弱只是预筛资源排序依据，不能替代后续入场/买点判断。

### 4.5 预筛总分与边界

```text
pre_screen_score =
  0.45*transmission_proxy
  + 0.25*quality
  + 0.20*valuation_attractiveness
  + 0.10*trend_health_score
```

`pre_screen_score` 保持在0–1之间，仅决定深度研究的同业排序。买点形态与风险计划由后续趋势研究独立确认。

**边界：** 本文件负责所有hard-eligible的硬过滤、轻量技术机会评分及前置三级行业动态Top5筛选与审计；只有入选者开展深度公司研究，最终每主题0至5只由趋势买点引擎在研究与风险判断之后确定。

---

## 5. 前置动态Top5及研究名额

1. 所有hard-eligible只消费同日期的紧凑量价特征，模型不重复阅读逐根日K；无核实结构、COOLING及FAILED不能占据新建仓研究名额。
2. 机会分=35%入场与结构失效风险+30%当前价格结构+20%量价有效性+15%相对强弱；综合分=70%机会分+30%原预筛分。阈值和比例暂属试运行，不能视为已证明最优。
3. 每三级行业按综合分前5名；第6名与第5名分差≤0.03可以增加且最多6名。不能因缺乏合格个股强行凑数。被排除和未入选者统一记录PRE_SCREENED_OUT，保留全量轻量审计。
4. 只对研究入选者做公司公告、主营主题传导、财务风险核验；已有明确NOT_SUPPORTED的股票不占名额，可依据同一行业的排序候补递补；未查明主题关联的入选者RESEARCH_PENDING，不能冒充业务审查已完成或用旧候选替换。
5. 正式主题榜再跨三级行业比较经核查的READY/WAIT股票，不超过每主题5只。高机会分不是买入信号，仍须独立确认入场区间和可验证失效价。

## 6. 覆盖及正式发布

- lightweight_scanned必须覆盖全部hard-eligible；selected+pre_screened_out必须精确划分，没有重复或遗漏。
- 只对前置动态Top5入选公司核实完整业务证据；未入选不计入UNCERTAIN或研究缺口。
- 入选但缺失公司业务核查须列出代码并阻断FORMAL发布，不得把SHADOW试算作为有效交易交接。
- 数据层提前计算一次全市场技术摘要，研究模型只读取所需短字段，避免全量逐根日K带来的开销。

# A股低风险买点榜｜预筛与深度研究范围

## 1. 职责边界

本文件只定义：

```text
Frozen Working Set
→ Company Hard Filter
→ Lightweight Peer Pre-screen
→ 每行业 Top5 / 并列第6
→ Deep Research Set
```

本文件不负责：
- 展开行业 Universe；
- 读取 company_industry_index；
- 读取 shard；
- 构造 working set。

这些由 `LOW_RISK_CANONICAL_FLOW.md` 在 Freeze 前完成。

---

## 2. 输入

唯一公司事实输入：

`frozen working_set[industry_code]`

要求 working set 已通过 Freeze Gate：

```text
working_set_company_count == universe_company_count
post_freeze_shard_read_count == 0
```

预筛阶段不得再次访问 company_industry_index、shard、screening group 或 Web。

---

## 3. 公司级硬过滤

只允许以下公司级硬条件：

- ST；
- 价格缺失、非数值或 <= 0；
- 净利润缺失或 <= 0；
- 关键估值、财务或趋势结构数据缺失；
- 营收同比 < -20% 且净利润同比 < -50%；
- 其他已在正式规则中明确的数据完整性硬条件。

禁止使用三级行业的 trend / strength / breadth / confidence / buyability 做准入或排序。

硬过滤发生在 frozen working set 内，不改变原 Universe 审计。

---

## 4. 轻量同业预筛

每家公司定义：

- `core_profit_yoy`：优先 `deduct_basic_eps_yoy`，缺失回退 `net_profit_yoy`；
- `non_core_eps_share_pct`：若 basic_eps 与 deduct_basic_eps 均可用，
  `abs(basic_eps-deduct_basic_eps)/max(abs(basic_eps),0.01)*100`；
- `cashflow_positive`：`operating_cashflow_per_share > 0`；
- `valuation_metric`：优先正 pe_ttm，其次正 pe_dynamic，再次正 pb；
- `position_pct`：60 日价格结构当前位置百分位。

同一三级行业、hard-eligible 公司之间计算 0–1 百分位：

- revenue_growth_pct：revenue_yoy 越高越优；
- core_profit_growth_pct：core_profit_yoy 越高越优；
- valuation_attractiveness：可用正估值越低越优；
- price_crowding_attractiveness：position_pct 越低越优。

质量：

```text
cashflow_score = 1 if OCF/share > 0 else 0

one_off_score =
  1.0 if non_core_eps_share_pct < 20%
  0.5 if unavailable
  0.0 if >= 20%

quality = 0.5*cashflow_score + 0.5*one_off_score
```

预筛：

```text
transmission_proxy =
  0.5*revenue_growth_pct
  + 0.5*core_profit_growth_pct

pre_screen_score =
  0.40*transmission_proxy
  + 0.25*quality
  + 0.20*valuation_attractiveness
  + 0.15*price_crowding_attractiveness
```

该分数只用于研究资源分配，不直接决定最终状态。

---

## 5. Deep Research 名额

1. 每个三级行业按 pre_screen_score 降序；
2. 原则上 Top5；
3. hard-eligible <=5 时全部进入；
4. 第6名与第5名绝对分差 <=0.03 时可并列进入；
5. 单行业最多6家；
6. 同一公司多路由命中只深研一次。

未入选：

`PRE_SCREENED_OUT`

这表示本轮不继续深研，不等于基本面否定，不计入 DROP。

---

## 6. Coverage

```text
pre_screen_processed_codes
==
all_hard_eligible_codes_in_frozen_working_sets
```

Deep Research Set：

```text
每行业 Top5 + 明确并列第6
的去重并集
```

随后：
- Transmission 只覆盖 Deep Research Set；
- Expectation 覆盖其中所有 Transmission=SUPPORTED；
- Risk–Reward 按后续规则闭合。

---

## 7. 正式结果

至少保存：

- `hard_filtered_out`
- `pre_screen_selected`
- `pre_screened_out`
- 每个 hard-eligible 公司的 pre_screen_score 或明确不可计算原因

若任何 hard-eligible 公司未完成预筛且无明确原因：
`pre_screen_coverage != COMPLETE`

不得因为已找到 READY 提前停止已入选公司的完整 coverage。

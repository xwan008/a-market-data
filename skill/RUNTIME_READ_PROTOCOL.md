# A股低风险买点榜｜V6 运行协议

本文件是正式执行契约。V6 的唯一顺序：

> **行业盈利/景气预资格 → 行业资金关注 → 公开研究产业领先变量 → 行业内寻找早启动/健康首次回踩 → 公司排雷 → 最终少数深研 → 发布。**

模型判断细则以同版本 `skill/SKILL.md` 为准。

---

## 1. 执行期正式输入

每次 19:00 正式版或手动正式触发，只读取当前 `main`：

- `skill/RUNTIME_READ_PROTOCOL.md`
- `skill/SKILL.md`
- `data/runtime/meta.json`
- `meta.candidate_file`

这四项是模型执行期唯一必读输入。

生成期大文件 `full_market_price_structure.json`、`industry_state.json`、`screening_groups.json` 不是执行期 Hard Gate 必读文件。

---

## 2. Runtime 的职责

V6 runtime 必须满足“行业先于股票”。

生成链应先在全市场行业层完成预资格：

```text
行业盈利基础：
PROFIT_TREND_CONFIRMED / EARNINGS_IMPROVING / EARNINGS_TRANSMITTING
+
行业资金：
FUNDS_ENTERING / FUNDS_ATTENTION
```

然后才扫描这些行业中的全部结构可用股票，并在股票层保留：

```text
PRE_BREAKOUT
ACCUMULATION_READY
FRESH_ACTIVATION
EARLY_EXPANSION
HEALTHY_FIRST_PULLBACK
REACCELERATION
```

正式 `meta.structural_rule.selection_mode` 必须等于：

```text
industry_first_leading_prosperity_then_stock
```

并且：

```text
meta.runtime_validation.industry_first_pool_applied == true
meta.runtime_validation.stock_lifecycle_gate_applied == true
```

旧 `industry_dual_confirm_then_early_stock` 视为 V5，不得作为 V6 正式输入。

---

## 3. Runtime Hard Gate

必须满足：

- `meta.runtime_validation.status == "passed"`；
- `industry_first_pool_applied == true`；
- `stock_lifecycle_gate_applied == true`；
- `meta.structural_rule.selection_mode == "industry_first_leading_prosperity_then_stock"`；
- `leading_prosperity_public_research_required == true`；
- `meta.snapshot.market_status == "closed"`；
- `meta.snapshot.trade_date == candidate_file.trade_date`；
- candidate 文件存在、可解析、code 唯一；
- `candidate_file.candidate_count == len(rows) == meta.candidate_count`；
- columns 与 `meta.candidate_columns` 一致；
- `selection_funnel.pre_lifecycle_rows >= post_lifecycle_rows == candidate_count`；
- `prequalified_industry_count` 存在并大于等于 `post_lifecycle_industry_count`；
- 每只候选的 `stock_lifecycle_stage` 属于 V6 合法集合。

如果 lifecycle 后候选为0，不视为 FAILED；发布“本轮无满足条件机会”。

---

## 4. 正式执行流程

```text
Bootstrap / Hard Gate
↓
Layer 1｜行业池复核
读取 runtime 中已经完成的盈利基础 + 资金预资格
↓
Layer 2｜产业领先变量研究【必须执行】
确认未来1–2季度的价格/价差/库存/订单/需求/产能/政策等
↓
只保留 LEADING_CONFIRMED / LEADING_EARLY 行业
↓
Layer 3｜行业内部个股复核
早启动 + 健康首次回踩；排除退潮/派发
↓
Layer 4｜公司轻量排雷
↓
Focused Deep Research 3–5只
↓
正式低风险买点榜
```

禁止回到“先从全市场个股技术形态选29只，再反推行业”的旧路径。

---

## 5. Layer 1｜行业预资格复核

对 runtime 中出现的每个行业说明：

### 盈利基础
使用：

- `industry_trend`
- `industry_strength`
- `industry_core_improving_breadth`
- `industry_aggregate_revenue_yoy`
- `industry_aggregate_parent_profit_yoy`
- `industry_confidence`

解释其属于：

- `PROFIT_TREND_CONFIRMED`
- `EARNINGS_IMPROVING`
- `EARNINGS_TRANSMITTING`

注意：`EARNINGS_TRANSMITTING` 不是弱化版 T1，而是“收入/需求先改善、利润仍在传导”的早期状态。

### 行业资金
使用：

- `industry_market_breadth`
- `industry_market_activity`
- `industry_market_confirmation`
- `industry_market_breadth_score`
- `industry_median_volume_ratio_vs_20d`
- `industry_expanding_volume_share`

解释其属于：

- `FUNDS_ENTERING`
- `FUNDS_ATTENTION`

在全市场风险释放环境中，不得因为绝对量比 <1 就机械否定一个明显相对强势、广度扩散的行业。

---

## 6. Layer 2｜产业领先变量研究【新增核心步骤】

对预资格行业做公开资料研究，不允许只凭仓库财报字段宣布“景气确认”。

每个行业原则上 1–3 次高质量定向查询，优先行业一手/权威来源，确认：

- 产品价格/价差；
- 库存与供需；
- 订单/排产/稼动率；
- 下游需求；
- 产能变化；
- 政策/资本开支；
- 原料涨价能否向下游传导；
- 最新业绩预告、出货、招投标、涨价函等。

输出：

- `LEADING_CONFIRMED`
- `LEADING_EARLY`
- `LEADING_WEAK`

只有前两类进入个股研究。

---

## 7. Layer 3｜行业内部个股复核

合法生命周期：

- `PRE_BREAKOUT`
- `ACCUMULATION_READY`
- `FRESH_ACTIVATION`
- `EARLY_EXPANSION`
- `HEALTHY_FIRST_PULLBACK`
- `REACCELERATION`

重点理解：

### `HEALTHY_FIRST_PULLBACK`
允许市场整体下跌把强行业股票带回合理价格，但必须满足：

- 所属行业领先逻辑/资金仍有效；
- 前期涨幅不过度；
- RS20 尚未明显转弱；
- 回撤靠近 MA20/支撑/成交密集区；
- 没有高位放量派发；
- 中期结构未破坏。

### 排除

- `POST_PEAK_FADE`
- `DISTRIBUTION_RISK`
- 高位下跌放量；
- 已完成大波段后的持续回落；
- 跌破核心平台/均线且相对强度同步恶化。

不得再用“距20日高点回撤5%”一刀切排除所有回踩。

---

## 8. Layer 4｜公司轻量排雷

检查：

- 公司收入/核心利润；
- 归母与扣非；
- 现金流；
- 一次性收益；
- 行业→公司传导；
- 重大减持/监管/诉讼/业绩预警/资本运作；
- 极端估值风险。

PE/PB 不做低估值排序。

---

## 9. Focused Deep Research

最终通常3–5只，不足不凑数。每家公司原则上2–4次定向公开查询，至少确认：

1. 最新主营/归母/扣非；
2. 利润改善来源；
3. 产业景气如何传导；
4. 为什么资金现在关注它；
5. 当前生命周期为什么不是退潮；
6. 近期重大风险。

关键事实无法确认时 `UNVERIFIED` 并移除。

---

## 10. 正式输出

### A.【本轮行业机会池】

```text
行业｜盈利阶段｜产业领先阶段｜行业资金阶段｜核心证据｜反向风险
```

### B.【正式低风险启动榜】

```text
股票｜行业｜产业景气｜行业盈利｜行业资金｜个股阶段｜状态｜当前价｜合理买入区间｜低风险买入区间｜失效价/条件｜第一阻力位｜深研结论｜核心风险
```

状态：

- `READY_TO_WATCH_ENTRY`
- `WAIT_PULLBACK`
- `OBSERVE`
- `EXCLUDE_FADE`
- `UNVERIFIED`

`HEALTHY_FIRST_PULLBACK` 可以成为 READY，但必须有明确低风险结构依据。

### C.【筛选漏斗】

至少给出：

- `prequalified_industry_count`
- `pre_lifecycle_rows`
- `post_lifecycle_rows`
- `post_lifecycle_industry_count`
- 最终产业领先变量确认行业数
- 最终深研数

---

## 11. 价格纪律

当前价使用正式 runtime 收盘价。

合理买入区间与低风险区间必须来自 MA、支撑、成交密集区、突破位、阻力和 invalidation。

健康回踩的低风险区优先靠近支撑/成交密集承接，而不是等待重新大涨后追确认。

不存在可靠区间写 `N/A`。

---

## 12. 完成与失败

满足以下即可发布：

- Hard Gate 通过；
- 完整消费 V6 runtime candidates；
- 行业领先变量研究完成；
- 生命周期复核完成；
- 公司排雷完成；
- 最终公司深研完成或无法确认者移除。

只有正式输入不可读、trade_date冲突、runtime validation失败、或关键工具完全不可用才允许整轮 FAILED。

没有机会不是失败；宁可0只，也不能回到错误选股路径。
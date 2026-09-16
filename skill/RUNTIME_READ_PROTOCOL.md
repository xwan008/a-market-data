# A股低风险买点榜｜V5 轻量运行协议

本文件是正式执行契约。V5 的唯一顺序是：

> **行业景气/盈利确认 → 行业资金确认 → 行业内寻找早启动股票 → 公司排雷 → 最终少数深研 → 发布。**

模型判断细则以同版本 `skill/SKILL.md` 为准。

---

## 1. 执行期正式输入

每次 19:00 正式版或手动正式触发，只读取当前 `main`：

- `skill/RUNTIME_READ_PROTOCOL.md`
- `skill/SKILL.md`
- `data/runtime/meta.json`
- `meta.candidate_file`

这四项是模型执行期唯一必读输入。

`full_market_price_structure.json`、`industry_state.json`、`screening_groups.json`、历史 Ledger/probe 都不是执行期 Hard Gate 必读文件。它们属于生成期来源或诊断视图。

---

## 2. Runtime 的职责

V5 runtime 不是“全市场技术候选”。它必须已经在构建阶段完成三层硬筛选：

```text
第一层：行业基本面门
T1_PROSPERITY_CONFIRMED / T2_PROFIT_TREND

第二层：行业资金门
FUNDS_TESTING / TREND_FORMING

第三层：个股生命周期门
PRE_BREAKOUT / ACCUMULATION_READY / FRESH_ACTIVATION / EARLY_EXPANSION / 严格REACCELERATION
```

正式 `meta.structural_rule.selection_mode` 必须等于：

```text
industry_dual_confirm_then_early_stock
```

且：

```text
meta.runtime_validation.industry_dual_confirm_gate_applied == true
```

否则属于旧 runtime，不得作为 V5 正式输入。

---

## 3. Runtime Hard Gate

必须满足：

- `meta.runtime_validation.status == "passed"`；
- `industry_dual_confirm_gate_applied == true`；
- `meta.structural_rule.selection_mode == "industry_dual_confirm_then_early_stock"`；
- `meta.snapshot.market_status == "closed"`；
- `meta.snapshot.trade_date == candidate_file.trade_date`；
- candidate 文件存在、可解析、code 唯一；
- `candidate_file.candidate_count == len(rows) == meta.candidate_count`；
- columns 与 `meta.candidate_columns` 一致；
- `selection_funnel.pre_gate_rows >= post_gate_rows == candidate_count`；
- 行业景气/盈利、行业资金、个股启动和价格结构核心字段存在。

如果 V5 gate 后候选为 0，不视为 FAILED；应发布“本轮无满足条件机会”。

不得因为生成期大文件无法直接读取而 FAILED。

---

## 4. 正式执行流程

```text
Bootstrap / Hard Gate
↓
Layer 1｜复核行业双确认
只处理 runtime 中已经通过 T1/T2 + 资金门的行业
↓
Layer 2｜复核个股早启动
确认不是 POST_PEAK_FADE / DISTRIBUTION
↓
Layer 3｜公司轻量排雷
↓
形成少量最终研究对象
↓
Focused Deep Research 3–5只
↓
正式低风险买点榜
```

不得重新从全市场寻找 runtime 之外的股票。

---

## 5. Layer 1｜行业双确认复核

按 `industry_code` 聚合候选，只回答两个问题：

### A. 行业为什么正在变好？
使用：

- `industry_trend`
- `industry_strength`
- `industry_core_improving_breadth`
- `industry_aggregate_revenue_yoy`
- `industry_aggregate_parent_profit_yoy`
- `industry_confidence`

正式行业必须可解释为 T1 或 T2。

### B. 为什么市场现在开始交易它？
使用：

- `industry_market_breadth`
- `industry_market_activity`
- `industry_market_confirmation`
- `industry_market_breadth_score`
- `industry_median_volume_ratio_vs_20d`
- `industry_expanding_volume_share`

正式行业必须可解释为 FUNDS_TESTING 或 TREND_FORMING。

如果某行数据与 V5 规则冲突，按更保守解释处理并从正式机会剔除，不得因为 runtime 已包含就机械保留。

---

## 6. Layer 2｜个股早启动复核

只在合格行业内部研究股票。

核心字段：

- `activation_tier`
- `day_change_pct`
- `volume_ratio_1d_vs_20d`
- `volume_ratio_5d_vs_20d`
- `relative_strength_20d_vs_market_pct`
- `return_10d_pct / return_20d_pct`
- `close_change_5d_pct`
- `high_20d`
- `ma20 / ma60`
- `position_pct`
- `breakout_confirmed`
- 支撑/成交密集区/阻力/失效位

模型必须计算并理解：

```text
drawdown_from_20d_high_pct = (high_20d - price) / high_20d * 100
```

重点寻找：PRE_BREAKOUT、ACCUMULATION_READY、FRESH_ACTIVATION、EARLY_EXPANSION。

`active_pullback` 默认不能成为正式新机会；只有满足 Skill 的严格 REACCELERATION 才可继续。

POST_PEAK_FADE / DISTRIBUTION_RISK 必须直接排除，不能放入 WAIT_PULLBACK。

成交量必须和价格方向一起解释。下跌放量不能自动视为资金流入。

---

## 7. Layer 3｜公司轻量排雷

只排除会破坏行业→公司传导的明显风险：

- 公司收入/核心利润恶化；
- 归母与扣非严重背离；
- 现金流明显冲突；
- 一次性收益主导；
- 行业改善但公司没有传导；
- 重大减持/监管/诉讼/业绩预警/资本运作；
- 极端估值且增长不足。

PE/PB 只做风险修正，不做低估值排序。

结束后只保留最终 3–5 只做公开深研；不足按实际数量继续。

---

## 8. Focused Deep Research｜必须真实执行

最终每家公司原则上 2–4 次定向公开查询，至少覆盖：

1. 最新主营收入、归母、扣非；
2. 利润变化来源与一次性收益；
3. 行业景气能否传导到公司；
4. 近期重大减持、监管、诉讼、业绩预警、重大资本运作；
5. 为什么资金是“现在”开始选择它。

优先公司公告、交易所、权威财经来源、行业一手来源。

不得只读 runtime 后直接宣称已完成深度研究。

单家公司无法确认时标记 `UNVERIFIED` 并移除，不拖垮整轮。

---

## 9. 正式输出

### A.【本轮行业双确认池】
按行业输出：

```text
行业｜景气阶段(T1/T2)｜行业盈利证据｜资金阶段(FUNDS_TESTING/TREND_FORMING)｜资金证据
```

### B.【正式低风险启动榜】
固定列：

```text
股票｜行业｜行业景气｜行业盈利｜行业资金｜个股阶段｜状态｜当前价｜合理买入区间｜低风险买入区间｜失效价/条件｜第一阻力位｜深研结论｜核心风险
```

状态只使用：

- `READY_TO_WATCH_ENTRY`
- `WAIT_PULLBACK`
- `OBSERVE`
- `EXCLUDE_FADE`
- `UNVERIFIED`

`EXCLUDE_FADE` 不给买入区间。

### C.【本轮筛选漏斗】
必须给出：

- runtime 生成前候选数 `pre_gate_rows`
- 行业双确认+生命周期后候选数 `post_gate_rows`
- 合格行业数 `eligible_industry_count`
- 最终深研数

用来验证系统是否真的先行业、后股票，而不是直接从个股挑。

---

## 10. 价格纪律

当前价必须使用正式 runtime 对应 `trade_date` 的收盘价。

合理买入区间、低风险买入区间、失效位、第一阻力位必须来自正式价格结构：MA、支撑、成交密集区、突破位、阻力、invalidation。

不存在可靠低风险区时写 `N/A`；不得为了形成榜单而制造价格。

当前价高于合理买入上沿，不得标记 READY。

---

## 11. 完成与失败

满足以下条件即可发布：

- Hard Gate 通过；
- 完整消费 V5 runtime candidates；
- 行业双确认复核完成；
- 个股生命周期复核完成；
- 公司排雷完成；
- 最终公司完成 Focused Deep Research，或无法确认者被移除。

只有四个正式输入不可读、trade_date 冲突、runtime validation 失败、或关键工具完全不可用才允许整轮 FAILED。

候选少、最终只有1只、甚至0只，都不是失败理由。

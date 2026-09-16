# A股低风险买点榜｜V4.1 轻量运行协议

本文件是正式执行契约。V4.1 的目标：

> **行业资金确认 → 行情生命周期过滤 → 个股方向性资金确认 → 轻量基本面排雷 → 最终 3–5 只 Focused Deep Research → 正式榜。**

具体判断细则以同一版本 `skill/SKILL.md` 为准。

---

## 1. 正式输入

每次 19:00 正式版或手动正式触发，只读取当前 main：

- `skill/RUNTIME_READ_PROTOCOL.md`
- `skill/SKILL.md`
- `data/runtime/meta.json`
- `meta.candidate_file`（通常 `data/runtime/candidates.json`）

这四项是执行期唯一必读正式输入。

以下均属于生成期来源/可选诊断，不得作为执行期 Hard Gate：

- `data/research/full_market_price_structure.json`
- `data/research/industry_state.json`
- `data/runtime/screening_groups.json`
- 历史 Ledger / probe / 旧榜单

生成期已经负责全市场数据、日期一致性、runtime validation；模型执行期不得重复读取巨型中间文件制造伪失败。

---

## 2. Runtime Hard Gate

必须满足：

- `meta.runtime_validation.status == "passed"`
- `meta.snapshot.market_status == "closed"`
- `meta.snapshot.trade_date == candidate_file.trade_date`
- candidate 可解析、code 唯一
- `candidate_count == len(rows) == meta.candidate_count`
- columns 与 `meta.candidate_columns` 一致
- 生命周期判断所需字段存在：`price/day_change_pct/high_20d/close_change_5d_pct/position_pct/ma20/volume_ratio_1d_vs_20d/volume_ratio_5d_vs_20d/relative_strength_20d_vs_market_pct`

只有执行期正式输入不可读、日期冲突或 runtime validation 失败，整轮才允许 FAILED。

---

## 3. 固定执行顺序

```text
Bootstrap / Runtime Hard Gate
↓
Layer 1｜Industry Money Flow
↓
Layer 2｜Lifecycle Gate
↓
Layer 3｜Directional Money Confirmation
↓
约 8–12 只真正仍有资金确认的候选
↓
Layer 4｜Light Fundamental Risk Filter
↓
最终 3–5 只
↓
Focused Deep Research
↓
正式榜
```

不得跳过 Lifecycle Gate，不得仅凭 activation_tier 直接进入公司研究。

---

## 4. Layer 1｜Industry Money Flow

从 candidate_file 按行业聚合。

`READY_TO_WATCH_ENTRY` 的行业原则上必须满足 `SKILL.md` 的 `TREND_FORMING`；`FUNDS_TESTING` 只能产生 OBSERVE，不能单独产生 READY。

行业基本面只做风险修正，不能替代市场成交/广度/扩散证据。

---

## 5. Layer 2｜Lifecycle Gate

对每只候选计算：

```text
drawdown_from_20d_high_pct = (high_20d - price) / high_20d * 100
```

然后按 `SKILL.md` 分类：

- `FRESH_ACTIVATION`
- `REACCELERATION`
- `ORDERLY_FIRST_PULLBACK`
- `POST_PEAK_FADE`
- `DISTRIBUTION_RISK`

`POST_PEAK_FADE` 和 `DISTRIBUTION_RISK` 是硬排除，不得进入最终深研池，不得出现在“低风险启动机会”或“等待回踩”。

特别注意：

- 从近期高点明显回撤但只是量能尚存，不等于新资金进入；
- 放量负收益/高位回撤优先解释为分歧或兑现风险；
- `active_pullback` 默认只允许 WAIT_PULLBACK/OBSERVE，只有新的 `REACCELERATION` 才能升级 READY。

---

## 6. Layer 3｜Directional Money Confirmation

成交量必须结合价格方向解释。

`STRONG_MONEY_CONFIRMATION` 按 `SKILL.md` 执行。仅有以下情况不够：

- 1日/5日量比接近 1；
- 过去曾经放过量；
- 当前相对强度尚可但正从高点退潮；
- 缩量反弹；
- 负涨幅的巨量日。

通过生命周期 + 资金确认后，目标保留约 8–12 只；不足时按实际数量继续，不凑数。

---

## 7. Layer 4｜Light Fundamental Risk Filter

只做结构化快速排雷：

- 收入与核心利润同步恶化
- 归母与扣非严重背离
- 经营现金流和盈利严重冲突
- 一次性/非核心收益主导
- 极端估值而核心增长不足
- 明显重大风险

PE/PB 不做低估值排序。

从剩余候选中选择最终 **3–5 只**进入 Focused Deep Research；不足 3 只时按实际数量研究，不凑数。

---

## 8. Focused Deep Research｜必须真实执行

最终 3–5 只，每家公司原则上进行 2–4 次定向公开查询，至少覆盖：

1. 最新财报/业绩预告中的主营、归母、扣非；
2. 利润变化来源及一次性收益风险；
3. 近期重大公告：减持、监管、诉讼、资本运作、业绩预警；
4. 行业景气/资金逻辑是否真的传导到公司；
5. 为什么市场现在选择它，而不是只说明公司长期质量。

优先公司公告、交易所/权威财经源、行业一手来源。

单家公司关键事实无法确认：标记 `UNVERIFIED` 并从正式可执行机会移除，然后继续其他公司。单家公司失败不得导致整轮 FAILED。

禁止只读取 runtime 后在几十秒内把 3–5 只全部视为“已深研”；正式输出必须能展示每只公司的深研事实摘要与来源依据。

---

## 9. 正式输出

### A. 本轮资金趋势行业
3–6 个真正仍有资金扩散的方向；区分 `TREND_FORMING` 与 `FUNDS_TESTING`。

### B. 正式低风险启动榜
只放通过生命周期、方向性资金、基本面与深研的股票。

固定列：

```text
股票｜状态｜当前价｜合理买入区间｜低风险买入区间｜失效价/条件｜第一阻力位｜生命周期｜资金确认｜启动证据｜深研结论｜核心风险
```

状态只允许：

- `READY_TO_WATCH_ENTRY`
- `WAIT_PULLBACK`
- `OBSERVE`
- `UNVERIFIED`
- `EXCLUDE_FADE`

`EXCLUDE_FADE` 只在“退出/排除说明”中出现，不得给买入区间。

### C. 退出/排除
只列会解释为什么某只看似强势股票实际上已经属于退潮/分歧的关键证据。

明确注明 trade_date、市场环境、原始候选数、生命周期后候选数、最终深研数。

---

## 10. 完成与容错

允许发布正式榜的条件：

- Hard Gate 通过
- 全部 runtime candidates 完成生命周期判断
- 行业资金聚合完成
- 方向性资金确认完成
- 轻量基本面排雷完成
- 最终 3–5 只已完成 Focused Deep Research，或无法确认者已剔除

不再要求 Frozen Ledger、G1/G2、多层 coverage、全候选 Deep Research。

但也不得为了追求速度跳过生命周期门或最终 3–5 只深研。

核心发布原则：

> **宁可最终只有 1–2 只，也不能把“上一波涨过、现在退潮”的股票包装成低风险买点。**

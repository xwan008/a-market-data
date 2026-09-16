# A股低风险买点榜｜V4 轻量运行协议

本文件是“A股低风险买点榜”的正式执行契约。V4 的目标不是完成投资委员会式全量研究，而是稳定、快速地完成：

> **行业资金趋势发现 → 个股早期启动确认 → 轻量基本面排雷 → 少量定向公开研究 → 发布。**

模型判断细则以同一版本的 `skill/SKILL.md` 为准。

---

## 1. 核心原则

V4 只有四条核心约束：

1. **资金趋势优先于低估值。** PE/PB 不再决定候选入口；
2. **只研究已经出现市场验证、但尚未明显过热的股票。** “低位但无人交易”不是机会；
3. **基本面用于排雷，不用于制造启动信号。**
4. **完整执行优先于研究深度。** 正式公开研究只分配给最终 5–8 只股票；单家公司研究失败不得拖垮整轮。

V4 明确废止旧流程中的 Frozen Pre-Research Ledger、Stage A 全候选逐只 Ledger、G1/G2/Q2-lite、多层 coverage、全候选 Deep Research、无限期 waiting_for_entry，以及低 PE 结构性优先级。

`research/pre_research_ledger.json` 与历史 probe 仅视为旧版历史文件，不是 V4 正式输入。

---

## 2. 正式输入｜执行期只依赖紧凑 runtime

每次 19:00 正式版或手动正式触发，模型只读取当前 `main` 下：

- `skill/RUNTIME_READ_PROTOCOL.md`
- `skill/SKILL.md`
- `data/runtime/meta.json`
- `meta.candidate_file`（通常为 `data/runtime/candidates.json`）

这四项是 V4 模型执行期的唯一必读输入。

以下文件属于生成期来源或可选诊断信息，不得作为模型执行期 Hard Gate 的必读条件：

- `data/research/full_market_price_structure.json`
- `data/research/industry_state.json`
- `data/runtime/screening_groups.json`
- 历史 Ledger / probe / 旧榜单

生成链已经负责校验全市场量价状态、行业状态与 snapshot/runtime 的日期一致性；只有这些生成期校验通过，才允许 `meta.runtime_validation.status == "passed"`。模型执行期不得重复读取巨型中间文件制造伪 FAILED。

candidate_file 已包含正式需要的行业资金、个股量价启动、相对强度、价格结构、支撑、成交密集区、阻力与失效字段。

### Runtime Hard Gate

必须满足：

- `meta.runtime_validation.status == "passed"`；
- `meta.snapshot.market_status == "closed"`；
- `meta.snapshot.trade_date == candidate_file.trade_date`；
- candidate 文件存在、可解析、code 唯一；
- `candidate_file.candidate_count == len(rows) == meta.candidate_count`；
- candidate columns 与 `meta.candidate_columns` 一致；
- candidate 中 `activation_tier` 属于 V4 合法集合；
- 行业资金、个股量价启动和价格阶梯所需的核心结构字段存在。

不得因为任何生成期大文件无法被模型连接器完整读取而判定 FAILED。

---

## 3. 执行流程

```text
Bootstrap / Runtime Hard Gate
↓
Layer 1｜Industry Money Flow
基于候选中携带的行业资金字段聚合判断
↓
保留约 5–10 个有效行业方向
↓
Layer 2｜Stock Activation
完整读取 runtime candidates
寻找资金已进入但尚未充分交易的股票
↓
形成约 15–25 只研究候选（不足时不凑数）
↓
Layer 3｜Light Fundamental Risk Filter
只排除明显基本面/盈利质量/极端估值风险
↓
选择最终 5–8 只公开研究对象
↓
Targeted Public Research
每家公司只确认关键风险与盈利真实性
↓
Price Ladder
为正式机会计算价格阶梯
↓
正式榜
```

### 3.1 Layer 1｜Industry Money Flow

从 candidate_file 按 `industry_code` 聚合，使用：

- `industry_market_breadth`
- `industry_market_activity`
- `industry_market_confirmation`
- `industry_market_breadth_score`
- `industry_median_volume_ratio_vs_20d`
- `industry_expanding_volume_share`

行业基本面只做风险修正，不作为资金趋势的替代证据。优先研究资金试探 / 趋势形成阶段；有效行业少于 5 个时按实际数量继续，不凑数、不 FAILED。

### 3.2 Layer 2｜Stock Activation

完整读取 candidate 文件，不形成逐只 Ledger。

合法 `activation_tier`：

- `starting_breakout`
- `pre_breakout`
- `accumulation_base`
- `early_trend`
- `active_pullback`

优先保留：行业资金趋势有效、`chase_risk != high`、20 日涨幅未透支、量能改善、相对市场强度不弱、失效位明确。

“价格低 + PE低 + 没有成交量改善”不得进入最终研究池。

### 3.3 Layer 3｜Light Fundamental Risk Filter

只回答：

> **有没有足以破坏这次交易逻辑的明显公司风险？**

快速检查收入与核心利润、归母与扣非背离、经营现金流、一次性/非核心收益，以及极端估值与增长不匹配。PE/PB 是风险修正，不是排序发动机。

最终只选 5–8 只进入公开研究；不足时按实际数量继续。

---

## 4. Targeted Public Research｜只研究最终 5–8 只

每家公司原则上只做 1–3 次定向查询，重点确认：

1. 最新报告期主营/扣非盈利是否可信；
2. 高增长是否来自重大一次性收益、投资收益或联营收益；
3. 是否存在重大减持、监管、诉讼、业绩预警、重大资本运作等直接风险；
4. 必要时确认行业逻辑能否传导到公司。

禁止为了“研究完整”扩展成长篇产业链、竞争格局、全历史估值研究。

单家公司无法可靠确认时标记 `UNVERIFIED` 并移出正式可执行机会，但继续完成整轮。

---

## 5. 发布状态

正式输出只使用：

### `READY_TO_WATCH_ENTRY`
行业资金趋势有效、个股启动已被量价验证、基本面无明显破坏性风险、当前价格没有进入高追涨区。

### `WAIT_PULLBACK`
逻辑有效，但当前价格偏离合理风险收益区、靠近阻力或冲高明显。等待的是价格回到可接受区域。

### `OBSERVE`
行业有效，但个股启动证据尚未完成。下一轮仍未改善即可自然退出。

### `UNVERIFIED`
关键公司事实无法可靠确认，不作为正式执行机会。

---

## 6. Price Ladder｜正式机会必须生成价格阶梯

完成定向公开研究后，对所有正式榜股票生成以下字段；具体计算纪律以 `skill/SKILL.md` 第 9 节为准。

### 必填字段

- `current_price`：本轮 runtime 的正式收盘价；
- `reasonable_entry_range`：在趋势仍有效、无需明显追高时的合理买入区间；
- `low_risk_entry_range`：更靠近有效支撑/成交承接/突破回踩位的保守买入区间；
- `invalidation_price_or_condition`：失效价或明确失效条件；
- `first_resistance`：第一有效阻力位；无可靠上方阻力且处于价格发现阶段时写 `PRICE_DISCOVERY`。

### 计算依据

只能使用本轮正式 runtime 中的：

- `price`
- `ma20 / ma60`
- `support_low / support_high / support_center`
- `volume_zone_low / volume_zone_high / volume_zone_center`
- `resistance_low / resistance_high / resistance_center`
- `invalidation_price / invalidation_direction`
- `activation_tier`
- `chase_risk`
- `distance_to_ma20_pct / distance_to_ma60_pct`
- `downside_to_invalidation_pct`
- breakout / relative-strength / volume confirmation 字段

公开研究只负责确认公司风险，不得因为“公司很好”抬高买入区间。

如果结构数据不足，必须写 `N/A` 并说明缺失依据，禁止猜测。

当前价高于合理买入区间上沿时，不得标记 `READY_TO_WATCH_ENTRY`，应降为 `WAIT_PULLBACK` 或 `OBSERVE`。

---

## 7. 完成条件与容错

满足以下条件即可发布正式榜：

- Runtime Hard Gate 通过；
- candidate 文件完整消费；
- 行业资金趋势聚合完成；
- 轻量基本面排雷完成；
- 最终 5–8 只完成定向研究，或将无法确认者标记 UNVERIFIED 并移除；
- 正式机会完成 Price Ladder。

不再要求全候选逐只 Deep Research、全候选逐只外部查询、Frozen Ledger、Gate coverage / Deep Research coverage 双闭合，或执行期直接读取全市场生成期大文件。

只有四个模型执行期正式输入不可读、校验失败或关键工具完全不可用且无法继续时，整轮才允许 FAILED。

---

## 8. 用户可见输出｜固定正式榜

正式版必须先给资金趋势行业摘要，然后输出一张固定榜单：

```text
股票｜状态｜当前价｜合理买入区间｜低风险买入区间｜失效价/条件｜第一阻力位｜启动证据｜核心风险
```

其中：

- 当前价必须对应本轮 `trade_date` 正式收盘价；
- 合理买入价和低风险价默认输出区间，不追求虚假精确；
- `WAIT_PULLBACK` 必须明确“等到哪里”；
- `OBSERVE` 若尚不存在可靠买点，可用触发条件替代强行给价格；
- 第一阻力位用于初始风险收益判断，不等于正式止盈目标。

正式版还可简要列：等待回踩、本轮退出/未确认，以及 trade_date / 市场环境 / 候选数量。

核心解释始终围绕：

> **资金为什么正在进入 → 个股为什么仍未充分交易 → 什么价格值得参与 → 什么条件会证明判断错误。**

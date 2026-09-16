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

V4 明确废止旧流程中的：

- Frozen Pre-Research Ledger；
- Stage A 全候选逐只模型 Ledger；
- G1 / G2 / Q2-lite 多层 Gate；
- `deep_read_codes` 全量 Deep Research；
- 为等待安全边际而无限期保留 `waiting_for_entry`；
- 因 PE 较低而获得结构性优先级。

`research/pre_research_ledger.json` 与历史 probe 仅视为旧版历史文件，不是 V4 正式输入。

---

## 2. 正式输入

每次 19:00 正式版或手动正式触发，读取当前 `main` 下：

- `skill/RUNTIME_READ_PROTOCOL.md`
- `skill/SKILL.md`
- `data/runtime/meta.json`
- `meta.candidate_file`（通常为 `data/runtime/candidates.json`）
- `data/research/industry_state.json`
- `data/research/full_market_price_structure.json`

`screening_groups.json` 仅允许作为可选诊断信息，不是必读输入，不得因为没有完整消费 screening groups 而阻止发布。

### Runtime Hard Gate

必须满足：

- `meta.runtime_validation.status == "passed"`；
- `snapshot.market_status == "closed"`；
- 正式输入 trade_date 一致；
- candidate 文件存在、可解析、code 唯一；
- `full_market_price_structure.reference_trade_date == trade_date`；
- candidate 中 `activation_tier` 属于 V4 合法集合。

只有输入不可读、日期不一致或校验失败才属于硬失败。

---

## 3. 执行流程

```text
Bootstrap / Runtime Hard Gate
↓
Layer 1｜Industry Money Flow
全行业判断资金试探与趋势形成
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
正式榜
```

### 3.1 Layer 1｜Industry Money Flow

必须以 `industry_state.json` 的市场证据为主：

- `market_breadth`
- `market_activity`
- `market_confirmation`
- `market_metrics.breadth_score`
- `market_metrics.median_volume_ratio_vs_20d`
- `market_metrics.expanding_volume_share`

行业基本面 `trend / aggregate_revenue_yoy / aggregate_parent_profit_yoy` 只做风险修正，不作为资金趋势的替代证据。

优先研究“资金试探 / 趋势形成”阶段；已明显过热或市场确认弱的行业不作为新机会核心来源。

### 3.2 Layer 2｜Stock Activation

完整读取 candidate 文件。candidate 文件按行可读时，可按 50 行一批读取，但不需要形成逐只 Ledger。

合法 `activation_tier`：

- `starting_breakout`
- `pre_breakout`
- `accumulation_base`
- `early_trend`
- `active_pullback`

优先保留：

- 行业资金趋势有效；
- `chase_risk != high`；
- 20 日涨幅尚未明显透支；
- 1 日或 5 日相对 20 日成交量已经改善；
- 相对市场强度不弱；
- 有明确失效位或可接受的下行风险。

“价格低 + PE低 + 没有成交量改善”不得进入最终研究池。

### 3.3 Layer 3｜Light Fundamental Risk Filter

这一层只回答：

> **有没有足以破坏这次交易逻辑的明显公司风险？**

只使用 runtime 结构化数据快速检查：

- 收入与核心利润是否同步明显恶化；
- 净利润增长是否与扣非 EPS 严重背离；
- 经营现金流是否与盈利明显冲突；
- 盈利是否可能被一次性/非核心收益主导；
- 估值是否极端到需要异常高增长才能解释。

PE/PB 是风险修正，不是排序发动机。低 PE 不自动加分。

这一层结束后只选 **5–8 只**进入公开研究；不足 5 只时按实际数量研究，不凑数。

---

## 4. Targeted Public Research｜只研究最终 5–8 只

每家公司原则上只做 1–3 次定向查询，重点确认：

1. 最新报告期主营/扣非盈利是否可信；
2. 高增长是否来自重大一次性收益、投资收益或联营收益；
3. 是否存在重大减持、监管、诉讼、业绩预警、重大资本运作等直接风险；
4. 必要时确认行业逻辑能否传导到公司。

禁止为了“研究完整”扩展成长篇产业链、竞争格局、全历史估值研究。

如果单家公司公开资料无法可靠确认：

- 标记 `UNVERIFIED`；
- 从正式可执行机会中移除；
- **继续研究其他公司并完成整轮任务。**

单家公司失败不是整轮 FAILED。

---

## 5. 发布状态

正式输出只使用：

### `READY_TO_WATCH_ENTRY`
行业资金趋势有效，个股启动已被量价验证，基本面没有明显破坏性风险，当前没有高追涨风险。

### `WAIT_PULLBACK`
行业和公司逻辑有效，但短期价格偏离低风险区域、靠近有效阻力或当日冲高，不追。

### `OBSERVE`
行业资金趋势有效，但个股启动证据仍不足。OBSERVE 不得因为“公司便宜”长期保留；下一轮没有新的资金验证即可自然退出。

不再建立无限期 `waiting_for_entry`。每轮都根据最新资金与价格结构重新判断；市场不验证，股票就退出。

---

## 6. 完成条件与容错

满足以下条件即可发布正式榜：

- Runtime Hard Gate 通过；
- candidate 文件完整消费；
- 行业资金趋势完成；
- 轻量基本面排雷完成；
- 对选中的最终 5–8 只完成定向研究，或将无法确认者标记 UNVERIFIED 并移除。

不再要求：

- 全候选逐只 Deep Research；
- 全候选逐只外部资料查询；
- Frozen Ledger；
- Gate coverage / Deep Research coverage 双闭合。

只有正式输入不可读、校验失败或关键工具完全不可用且无法继续时，整轮才允许 FAILED。

---

## 7. 用户可见输出

正式版保持精简：

1. **本轮资金趋势行业**：3–6 个最值得关注的早期行业；
2. **低风险启动机会**：通常 3–8 只，包含状态、启动证据、基本面排雷结论、关注区间/失效位；
3. **等待回踩**：逻辑仍在但当前不适合追；
4. **本轮退出/未确认**：只列真正影响上轮判断的变化；
5. 明确注明 trade_date 与市场环境。

核心解释始终围绕：

> **资金为什么正在进入 → 个股为什么仍未充分交易 → 什么条件会证明判断错误。**

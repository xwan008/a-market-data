# A股低风险买点榜｜模型判断规则

## 1. 目标

目标是：

> **从趋势榜已经发现的市场主线中，寻找未来 1–2 个季度盈利改善有事实基础、尚未被市场充分定价，并且当前下行风险可控的公司。**

主线：

```text
Trend Handoff
→ Routing
→ Transmission
→ Expectation
→ Risk–Reward
→ READY / WAIT / UNCERTAIN / DROP
```

---

## 2. Trend Handoff / Routing

买点榜读取 `research/trend_handoff.json`，获得趋势主题、产业状态、市场生命周期状态和申万三级行业代码，并完整展开对应 runtime company universe。

若趋势主题无法通过 handoff 自带的三级行业代码解析，可读取 `research/theme_routing_fallback.json` 中的显式主题路由。Fallback 只允许保存人工确认的行业代码或公司代码，并且所有代码都必须在当前 runtime 中验证；无法验证的映射保持 unresolved。

行业代码和主题 fallback 只承担路由功能。

同一公司可以继承多个 trend signals。

handoff 透传：

- `trend_state`：T0 / T1 / T2；
- `market_state`：观察 / 候选趋势 / 趋势确认 / 高潮或衰退等市场生命周期状态。

`market_state` 作为 Expectation 的市场定价上下文。

---

## 3. Transmission｜谁真正吃到趋势

对 routed universe 每家公司都问：

> **趋势为什么会让这家公司未来 1–2 个季度赚得更多？**

状态：

- `SUPPORTED`
- `NOT_SUPPORTED`
- `UNCERTAIN`

高质量前瞻证据包括：

- 已签或在手订单及明确交付窗口；
- 产品价格/价差已经变化；
- 销量、出货或产能利用率变化；
- 新产能已经投产并进入爬坡；
- 客户定点、认证或份额变化；
- 库存周期已发生反转；
- 产品结构改善可验证。

仅有“属于该板块”不算证据。

历史 PE、ROE、当期利润、现金流、一次性收益等用于解释公司质量与风险，但前瞻传导优先回答未来 1–2 个季度的盈利变化。

当历史财报很差、但已有明确未来订单/交付/价格驱动时，应继续验证未来传导。

`NOT_SUPPORTED` → `DROP`。

`UNCERTAIN` 最多允许一次针对关键缺口的定向补查；仍无法确认则保留 `UNCERTAIN`。

---

## 4. Expectation｜市场已经交易了多少

Transmission `SUPPORTED` 后，重建事件—价格—财务时间链：

```text
催化出现
→ 市场开始交易
→ 股价重估
→ 订单/价格/销量进入财务报表
→ 当前还有多少新增预期
```

预期阶段：

### EARLY
催化已经发生，但财务尚未充分体现，股价也尚未明显重估。

### CONFIRMING
订单/价格/销量开始兑现，盈利逻辑获得初步确认，股价开始反应，但未来 1–2 个季度仍有可验证增量。

### PRICED_IN
主要催化已经推动股价显著重估，随后财报大量兑现，市场认知已经较充分，新增惊喜有限。

### EXHAUSTED
利好或高增长数字仍在公布，但股价不再确认、开始回落，或核心驱动的边际改善已经转弱。

### UNCERTAIN
催化时间、财务兑现或市场定价证据存在关键缺口/冲突。

判断规则：

1. 不用单日涨跌判断预期阶段；
2. 股价从高点大跌本身不能证明出现新的预期周期；
3. 财报同比高增本身不能证明未来仍有预期差；
4. `PRICED_IN / EXHAUSTED` 若没有新的独立催化或预期重置，进入 `WAIT_EXPECTATION`；
5. 若旧预期出清后出现独立、可验证的新驱动，可建立新的 EARLY/CONFIRMING 周期，并重新进入 Risk–Reward；
6. 至少记录一条最可能推翻当前 expectation_stage 的反向证据。

`WAIT_EXPECTATION` 是 `WAIT` 的原因标签。

---

## 5. Risk–Reward｜最后讨论价格

完整 Risk–Reward 研究对象：

- Transmission = `SUPPORTED`；且
- Expectation = `EARLY / CONFIRMING`；或
- 有充分证据证明出现新的独立预期重置。

进入 Risk–Reward 后：

```text
未来 1–2 季度驱动
→ 前瞻/正常化盈利区间
→ 盈利中枢 × 保守估值
→ conservative fair value
→ low-risk buy range
→ downside anchor
→ conservative upside
```

原则：

1. 强周期公司使用正常化盈利；
2. 当前历史 PE 是背景，估值要匹配未来可持续盈利；
3. 正式 fair value 默认用“正常化盈利中枢 × 可辩护保守估值”；
4. 盈利下沿 × 估值下沿只作 stress floor；
5. 原则上 `conservative_upside >= 15%`；
6. 当前价原则上应在低风险区附近，或存在同等可量化下行保护；
7. 必须给出失效条件。

---

## 6. 最终状态

### READY
同时满足：

- Transmission = SUPPORTED；
- Expectation = EARLY / CONFIRMING，或有充分证据证明出现新的独立预期重置；
- 未来驱动可验证；
- 风险收益合格；
- 当前价格具备安全边际。

READY 不代表下一交易日一定上涨。

### WAIT
核心逻辑成立，但价格、预期阶段、安全边际或催化时点尚不合适。

原因标签：

- `WAIT_EXPECTATION`
- `WAIT_PRICE`
- `WAIT_MARGIN`
- `WAIT_CATALYST`

### UNCERTAIN
关键传导、预期阶段或正常化盈利存在无法消除的实质缺口/冲突。

### DROP
趋势无法实质传导到公司、核心逻辑被事实反证，或风险收益结构性不成立。

---

## 7. 研究纪律

- routed universe 全覆盖；
- 不设 Top N；
- 不设行业配额；
- 不因为已找到 READY 就提前停止；
- 不用单一 PE / PB / ROE / K线位置 / 当期利润增速决定状态；
- 不把 Web 热度当成传导证据；
- 优先公司公告、交易所披露、正式财报、投资者关系记录等一手证据；
- 对前瞻催化区分“已经发生的事实”与“管理层目标/机构预测”；
- 每家公司都记录关键 falsifier。

---

## 8. 正式输出字段

```text
股票｜趋势主题｜趋势状态｜市场状态｜三级行业｜预期阶段｜状态｜WAIT原因｜当前价｜合理价值区｜低风险区｜传导/催化证据｜市场已定价证据｜失效条件｜核心风险
```

- READY 以及因价格/安全边际等待的 WAIT 给出可辩护的价值区与低风险区；
- `WAIT_EXPECTATION` 在没有新预期重置时可写价值区 `N/A`；
- 无可靠价值区或低风险区时写 `N/A`。

最终正式机会集合不设固定数量或上限。

# A股低风险买点榜｜模型判断规则

## 1. 职责边界

本文件只定义公司级研究判断：

```text
Transmission
→ Expectation
→ Risk–Reward
→ READY / WAIT / UNCERTAIN / DROP
```

本文件**不定义**：
- routed 行业如何展开公司；
- Universe 来源；
- shard / cache / working set 的读取方式；
- 预筛 Top5/6 的执行范围；
- 价格区间具体估值算法。

这些分别由以下文件负责：

- 主流程：`LOW_RISK_CANONICAL_FLOW.md`
- 预筛：`PRE_SCREEN_RESEARCH_SCOPE_OVERRIDE.md`
- 估值：`INDUSTRY_ADAPTIVE_VALUATION_OVERRIDE.md`
- 价格区间：`PRICE_RANGE_OUTPUT_OVERRIDE.md`
- 执行效率：`EXECUTION_EFFICIENCY_OVERRIDE.md`

---

## 2. Transmission｜趋势是否真正传导到公司

只对预筛选中的 deep-research 公司判断：

> 趋势为什么会让这家公司未来 1–2 个季度赚得更多？

状态：

- `SUPPORTED`
- `NOT_SUPPORTED`
- `UNCERTAIN`

优先前瞻证据：

- 已签/在手订单及交付窗口；
- 产品价格/价差变化；
- 销量/出货变化；
- 新产能投产与爬坡；
- 客户定点/认证；
- 库存周期变化；
- 市占率或产品结构变化。

“属于该板块”本身不足以证明传导。

历史 PE、PB、ROE、当期利润、现金流和一次性收益用于解释公司质量与风险，不替代前瞻传导。

`NOT_SUPPORTED → DROP`。

`UNCERTAIN` 最多允许一次针对明确证据缺口的定向补证；仍无法确认则保留 UNCERTAIN。

---

## 3. Expectation｜市场已经交易了多少

仅对 Transmission=`SUPPORTED` 的公司重建：

```text
催化出现
→ 市场开始交易
→ 股价重估
→ 订单/价格/销量进入财务
→ 当前还有多少新增预期
```

阶段：

- `EARLY`
- `CONFIRMING`
- `PRICED_IN`
- `EXHAUSTED`
- `UNCERTAIN`

定义：

- EARLY：催化已出现，但财务和股价尚未充分反映；
- CONFIRMING：基本面开始兑现，未来 1–2 季度仍有可验证增量；
- PRICED_IN：主要催化已推动显著重估，新增惊喜有限；
- EXHAUSTED：利好仍在公布但股价不再确认，或核心驱动边际转弱；
- UNCERTAIN：事件—价格—财务时间链存在关键缺口或冲突。

不得仅凭单日涨跌或单一技术位置判断 expectation。

---

## 4. Risk–Reward｜最后讨论价格

完整 Risk–Reward 对象：

```text
Transmission = SUPPORTED
AND
(
  Expectation in {EARLY, CONFIRMING}
  OR 新的独立预期重置成立
)
```

估值与价格区间必须调用行业自适应估值与价格区间规则，不再默认要求完整 DCF。

基本链：

```text
未来1–2季度可验证驱动
→ 行业适配估值锚
→ 公司质量修正
→ fundamental anchor
→ 市场结构锚
→ reasonable price range
→ safety margin
→ low-risk buy range
```

强周期公司必须使用正常化盈利思想，不得用周期峰值利润简单外推。

必须记录最可能推翻当前结论的事实与失效条件。

---

## 5. 最终状态

### READY

同时满足：
- Transmission = SUPPORTED；
- Expectation = EARLY / CONFIRMING，或存在独立预期重置；
- 未来驱动可验证；
- 估值与风险收益合格；
- 当前价格具备足够安全边际。

READY 不代表下一交易日一定上涨。

### WAIT

核心逻辑成立，且已形成完整可辩护价格区间，但当前价格、预期、安全边际或催化时点尚不合适。

标签：
- `WAIT_EXPECTATION`
- `WAIT_PRICE`
- `WAIT_MARGIN`
- `WAIT_CATALYST`

### UNCERTAIN

关键传导、预期阶段、盈利质量、行业关键估值变量或估值锚之间存在无法消除的实质缺口/冲突。

### DROP

趋势无法实质传导到公司，核心逻辑被事实反证，或风险收益结构性失效。

---

## 6. 研究纪律

- 只研究预筛选中的 deep-research 公司；
- 不因为已找到 READY 就提前停止其他已入选公司的 coverage；
- 不用单一 PE / PB / ROE / K线位置 / 当期利润增速决定最终状态；
- 不把 Web 热度当成 Transmission 证据；
- 优先公司公告、交易所披露、正式财报和投资者关系记录等一手证据；
- 区分“已发生事实”与“管理层目标/机构预测”；
- 每家公司都记录关键 falsifier；
- 无法形成可靠价格区间时不得保留 READY / WAIT，应进入 UNCERTAIN。

---

## 7. 输出语义

READY / WAIT 必须输出：
- current_price
- reasonable_price_range
- low_risk_buy_range
- price_range_basis
- reentry_trigger
- transmission_evidence
- invalidation

价格区间不得写 N/A / 待估值 / 待确认。

具体字段和发布 Gate 以 `PRICE_RANGE_OUTPUT_OVERRIDE.md` 为准。

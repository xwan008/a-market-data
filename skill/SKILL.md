# A股低风险买点榜｜V4.1 模型判断规则

## 1. 目标

寻找：

> **行业资金正在形成趋势，个股处于“刚被资金发现”的早期启动或二次再加速，而不是上一轮上涨后的退潮，同时没有明显基本面破坏性风险的 A 股机会。**

支配逻辑：

> **先判断资金往哪里流，再判断这只股票处在行情生命周期的哪一段，只有“新启动/再加速”才研究，最后用基本面和公开资料决定能不能参与。**

低 PE、低位置、历史强势、过去曾放量，都不能替代“当前仍有新资金确认”。

---

## 2. 行业资金门｜先确认板块现在真的有钱

正式行业证据：

- `industry_market_breadth`
- `industry_market_activity`
- `industry_market_confirmation`
- `industry_market_breadth_score`
- `industry_median_volume_ratio_vs_20d`
- `industry_expanding_volume_share`

行业基本面只做风险修正，不得替代市场证据。

### 2.1 `TREND_FORMING`｜可产生正式机会

满足以下之一：

1. `industry_market_confirmation == strong`，且 breadth 不是 narrow；
2. `market_activity == active` 且 breadth 为 broad/divergent，同时：
   - `industry_median_volume_ratio_vs_20d >= 1.10`
   - `industry_expanding_volume_share >= 0.60`

### 2.2 `FUNDS_TESTING`｜只能观察，不能单独产生 READY

行业 breadth 改善，但成交仍只是 normal/neutral，或行业量比接近 1 而没有明显扩张，只能视为资金试探。

典型情况：broad + normal + neutral、行业量比约 0.9–1.1。此类行业中的个股即使技术结构尚可，也不得仅凭此进入 `READY_TO_WATCH_ENTRY`。

---

## 3. 行情生命周期门｜先判断“刚启动”还是“涨完在退潮”

对每只候选先计算：

```text
drawdown_from_20d_high_pct = (high_20d - price) / high_20d * 100
```

并联合：

- `position_pct`
- `close_change_5d_pct`
- `day_change_pct`
- `volume_ratio_1d_vs_20d`
- `volume_ratio_5d_vs_20d`
- `relative_strength_20d_vs_market_pct`
- `ma20`
- `breakout_confirmed`

先判生命周期，再看 activation_tier。

### 3.1 `FRESH_ACTIVATION`｜优先

满足启动/突破结构，且：

- 从 20 日高点回撤通常 <= 3%；
- 当前或近 5 日成交量明显扩张；
- 相对强度为正或明显改善；
- 价格没有明显跌回突破前结构。

### 3.2 `REACCELERATION`｜允许

股票曾经上涨并回踩，但只有出现**新的资金二次确认**才重新获得资格：

- 当日涨幅 > 0；
- `volume_ratio_1d_vs_20d >= 1.30`，优先 >= 1.50；
- `close_change_5d_pct` 不再明显为负；
- 当前价格重新站稳 MA20/关键平台；
- 不能只是缩量反弹。

### 3.3 `ORDERLY_FIRST_PULLBACK`｜只能 WAIT_PULLBACK

第一次健康回踩可以跟踪，但在重新放量转强前不得列为正式 READY：

- 趋势没有破坏；
- 回撤有限；
- 回踩缩量而不是放量下跌；
- 仍守住 MA20/突破平台附近；
- 行业资金趋势仍有效。

### 3.4 `POST_PEAK_FADE` / `DISTRIBUTION_RISK`｜硬排除

以下任一出现，禁止进入最终 3–5 只深研池：

1. `drawdown_from_20d_high_pct >= 5%`，且没有满足 `REACCELERATION`；
2. `drawdown_from_20d_high_pct >= 3%` 且 `close_change_5d_pct < 0`，同时当日量能没有新的强确认；
3. `day_change_pct < 0` 且 `volume_ratio_1d_vs_20d >= 1.50`，同时价格距离 20 日高点已回撤 >= 3%——优先解释为高位分歧/兑现风险，而不是“资金流入”；
4. `position_pct >= 70` 且已从近期高点明显回落，又没有新的放量上涨确认；
5. 曾经放量突破，但当前已经跌回关键平台/MA20 下方且 5 日方向转弱。

**成交量本身没有正负含义。放量上涨、放量突破可以是资金确认；放量下跌、放量冲高回落、突破后大幅回撤可能是兑现。不得把“大成交量”机械等同于“资金进入”。**

---

## 4. 个股资金确认门｜只有当前资金行为有效才继续

### 4.1 `STRONG_MONEY_CONFIRMATION`

满足以下之一：

- `starting_breakout` + `breakout_confirmed == true`，并且 `volume_ratio_1d_vs_20d >= 1.30`；
- `day_change_pct > 0` + `volume_ratio_1d_vs_20d >= 1.30` + `relative_strength_20d_vs_market_pct > 0`，且回撤自 20 日高点 <= 3%；
- `close_change_5d_pct >= 2%` + `volume_ratio_5d_vs_20d >= 1.15` + 相对强度为正，且没有 `POST_PEAK_FADE`；
- `REACCELERATION` 条件完整成立。

### 4.2 `WEAK_OR_OLD_CONFIRMATION`

以下只能 OBSERVE / WAIT_PULLBACK：

- 只有 `volume_ratio_5d_vs_20d >= 0.9` 或接近 1；
- 只有过去某天放过量，但当前量能和价格方向已经减弱；
- 只有相对强度尚可，但价格正从近期高点回落；
- `active_pullback` 尚未出现新的再加速确认。

V4.1 不再允许“资金没有明显撤退”被解释为“资金正在进入”。

---

## 5. activation_tier 的新语义

- `starting_breakout`：可成为 READY，但必须通过行业资金门、生命周期门和强资金确认门。
- `pre_breakout`：高优先观察；真正突破放量后才能 READY。
- `accumulation_base`：量先于价、仍处底部平台，可重点观察；需要持续量能而非单日脉冲。
- `early_trend`：只有仍接近新高/刚离开平台且资金继续增强才有效；若已经从高点明显回落则视为旧趋势，不得因名称是 early_trend 自动加分。
- `active_pullback`：默认不进入 READY；只有形成 `REACCELERATION` 后才能升级。

`activation_tier` 是结构标签，不是最终结论。

---

## 6. 轻量基本面排雷

市场结构通过后才做公司排雷，只回答：有没有明显事实会破坏当前交易逻辑？

重点检查：

- 收入与扣非核心利润是否同步明显恶化；
- 归母高增长是否被一次性/投资/联营收益主导；
- 经营现金流与盈利是否严重背离；
- ROE、核心增长与估值是否出现极端不匹配；
- ST、退市风险、重大监管/诉讼/减持/业绩预警。

PE/PB 只是风险修正。低 PE 不加分。

---

## 7. 研究池与真正的定向深研

流程固定为：

```text
runtime candidates
→ 生命周期 + 方向性资金门
→ 约 8–12 只“当前仍有资金确认”的候选
→ 轻量基本面排雷
→ 最终 3–5 只 Focused Deep Research
→ 正式榜
```

最终 **3–5 只**必须做真正的定向深研，而不是只读 runtime 后直接出榜。每家公司至少覆盖：

1. 最新财报/业绩预告：主营、归母、扣非；
2. 利润变化的主要来源，是否存在一次性收益；
3. 最近重要公告：减持、监管、诉讼、重大资本运作、业绩预警；
4. 行业资金/景气逻辑为什么能传导到该公司；
5. 为什么“现在”有资金选择它，而不是只说明公司长期不错。

原则上每家公司使用 2–4 次定向公开查询；优先公司公告、交易所/权威财经源、行业一手来源。资料冲突时必须说明。

深研不能修复市场结构失败：如果股票已是 `POST_PEAK_FADE` / `DISTRIBUTION_RISK`，即使公司基本面很好也不得放回正式榜。

---

## 8. 最终状态

### `READY_TO_WATCH_ENTRY`
必须同时满足：

- 行业为 `TREND_FORMING`；
- 生命周期为 `FRESH_ACTIVATION` 或 `REACCELERATION`；
- `STRONG_MONEY_CONFIRMATION` 成立；
- 未处于高追涨风险；
- 基本面排雷和 Focused Deep Research 通过。

### `WAIT_PULLBACK`
行业和公司逻辑有效，但当前价格偏高，或属于 `ORDERLY_FIRST_PULLBACK` 尚未出现二次资金确认。等待的是新的价格/资金触发，不是无限期等待。

### `OBSERVE`
行业或个股尚处资金试探，证据不够强。下一轮没有增强就自然退出。

### `UNVERIFIED`
关键公开事实无法确认，不得作为正式执行机会。

### `EXCLUDE_FADE`
已属于退潮、失败突破或高位分歧兑现结构。不得出现在“低风险启动机会”或“等待回踩”中。

---

## 9. 正式榜价格阶梯｜必须输出

每只正式机会固定输出：

```text
股票｜状态｜当前价｜合理买入区间｜低风险买入区间｜失效价/条件｜第一阻力位｜生命周期｜资金确认｜启动证据｜深研结论｜核心风险
```

### 当前价
使用本轮正式 runtime `price`，注明 `trade_date`。

### 合理买入区间
在行业资金、生命周期和资金确认仍有效时，不明显追高的常规参与区间。结合 MA20/MA60、支撑、成交密集区、突破位、阻力与失效位。

### 低风险买入区间
比合理区间更保守，优先靠近已验证支撑、成交承接或有效突破回踩位。若不存在可靠低风险区，写 `N/A`，不得硬造数字。

### 失效价/条件
优先使用 runtime `invalidation_price`；没有可靠数值时给明确结构失效条件。

### 第一阻力位
优先使用 runtime resistance 区；价格发现阶段写 `PRICE_DISCOVERY`，不虚构目标价。

价格纪律：

- 默认给区间，不给伪精确单点；
- 当前价高于合理区间上沿时不得 READY；
- `EXCLUDE_FADE` 不生成买入区间；
- 深研结论不得用于抬高技术买点。

---

## 10. 退出逻辑

以下任一发生即退出或降级：

- 行业 breadth/activity/volume 扩散明显转弱；
- 从 20 日高点进入 `POST_PEAK_FADE`；
- 放量下跌或放量高位分歧形成 `DISTRIBUTION_RISK`；
- 个股量能改善消失且相对强度下降；
- 跌破关键平台/MA20/正式失效位；
- 新公开信息显示核心盈利失真或基本面破坏。

不允许因为“之前强过”“PE 很低”“公司长期不错”继续保留。

---

## 11. 输出哲学

正式榜必须回答：

> **这是新资金正在建立位置，还是旧行情正在退潮？为什么判断是前者？如果判断错了，什么价格/行为会证明我们错了？**

回答不了这三个问题的股票，不进入正式榜。

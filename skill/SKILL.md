# A股低风险买点榜

## 1. 核心目标

寻找：

> **基本面没有明显恶化，当前价格经过价值与价格结构双重验证后具备安全边际，向下剩余空间有限，而未来 1–2 个季度保守上行空间充足的 A 股公司。**

核心原则：

> **先看还能跌多少，再看能涨多少。**

本榜单不是找走势最强、公司最优秀或最早转强的股票，而是找当前价格下风险收益最不对称的股票。

---

## 2. 总体职责边界

### 程序负责确定性复杂度

程序已经完成：

- 全市场数据完整性校验；
- 机械风险粗筛；
- 支撑距离、支撑触碰次数计算；
- 成交密集区距离、成交占比计算；
- 60 日价格位置计算；
- 正式结构硬筛；
- 申万三级行业映射；
- 生成 `candidates.json`；
- 生成按三级行业整理的 `peer_groups.json`；
- 生成公司级结构化事实视图 `company_research_view.json`；
- 计算不需要模型解释的机械标签，例如利润 / 扣非方向背离、利润增长但经营现金流为负等。

程序不做：

- 综合评分；
- 全市场 Top N；
- 每组 Top1 / Top2；
- 同行支配结论；
- 公司最终优劣结论；
- 最终估值、安全区和买卖建议。

> **能100%用公式确定的，不交给模型；需要解释、权衡和公开研究的，才交给模型。**

---

## 3. 当前结构硬筛

### 深低位：`position_pct <= 20%`

至少满足一种高质量承接：

- strong support：距 `support_center <= 3%`，且 `support_touches >= 3`；
- strong volume zone：距 `volume_zone_center <= 3%`，且 `volume_zone_share_pct >= 12%`。

### 中低位：`20% < position_pct <= 35%`

必须同时：

- 距 `support_center <= 5%`；
- 距 `volume_zone_center <= 5%`。

`position_pct > 35%` 不进入 model-ready candidates。

结构硬筛只回答：

> **当前价格结构是否值得占用后续研究预算。**

它不是最终 `low_risk_buy_range`，也不能替代公司研究。

---

## 4. 正式输入

正式运行分层使用：

- `data/runtime/meta.json`
- `meta.peer_group_file`：第一阶段同行轻比较；
- `meta.company_research_file`：第二阶段结构化公司预筛；
- `meta.candidate_file`：第三阶段幸存者需要完整确定性背景时按需使用；
- `skill/RUNTIME_READ_PROTOCOL.md`
- `skill/SKILL.md`

不再读取：

- `data/runtime/details/{code}.json`
- `data/runtime/screening_snapshot.json`
- `data/runtime/industry_state_compact.json`

peer view 与 company research view 都必须和 `candidates.json` 股票全集完全一致；它们只是把同一批确定性事实换成更适合模型处理的组织方式。

---

## 5. 正式研究漏斗

```text
机械候选
  ↓
程序结构硬筛
  ↓
model-ready candidates
  ↓
程序 peer_groups
  ↓
第一阶段：同行组轻量支配判断
  ├─ CLEARLY_DOMINATED → excluded
  └─ 单只组 / NOT_CLEARLY_DOMINATED
                 ↓
       第二阶段：company_research_view
       结构化公司预筛，不联网
       ├─ CLEARLY_WEAK → excluded
       ├─ PASS_TO_DEEP_RESEARCH
       └─ UNCERTAIN
                 ↓
       第三阶段：少量公开 Deep Research
                 ↓
       正常化估值 + 最终安全区
                 ↓
       正式榜 / waiting / research_uncertain / excluded
```

关键变化：

> **Deep Research 不再覆盖全部 research candidates。它是最后的昂贵验证层，而不是批量初筛层。**

---

## 6. 第一阶段：同行组轻量比较

### 6.1 单只组

如果某三级行业只有 1 只候选：

- 不存在同组同行可以形成明确支配；
- 不需要额外同行推理；
- 直接进入第二阶段结构化公司预筛。

### 6.2 多只组

只比较程序已经整理好的三类事实。

#### A. 价格结构

主要看：

- `position_pct`
- `support_distance_pct`
- `support_touches`
- `volume_zone_distance_pct`
- `volume_zone_share_pct`
- `resistance_center`
- invalidation

这些公司都已通过结构硬筛，所以第一阶段比较的是**相对结构质量**，不是重新计算准入规则。

#### B. 估值质量

联合看：

- PE-TTM
- 动态 PE
- PB
- ROE
- 盈利增长

不得孤立比较 PE / PB。低 PE 可能来自周期盈利高点；较高 PB 如果对应更高且可持续 ROE，也不能机械认定更差。

#### C. 经营质量

主要看：

- 营收同比
- 净利润同比
- 扣非 EPS 同比
- 经营现金流 / 股
- 毛利率

第一阶段只回答：

> **同组内是否存在明确支配关系？**

不是选最好公司，不是排序，也不做公司长篇研究。

---

## 7. 第一阶段明确支配规则

候选 A 只有在存在同组候选 B 且同时满足时，才允许前置排除：

1. B 在价格结构、估值质量、经营质量三个维度中没有一个维度明显弱于 A；
2. B 至少在一个维度明显更优；
3. A 不存在 B 无法覆盖的明显差异化优势；
4. 不存在业务异质性、周期失真或数据冲突，需要进一步研究才能解决。

第一阶段只允许：

- `CLEARLY_DOMINATED`
- `NOT_CLEARLY_DOMINATED`

只要互有胜负、不可比或无法可靠判断，就 `NOT_CLEARLY_DOMINATED`。

如果判定 `CLEARLY_DOMINATED`，至少说明：

- `dominated_by`
- 价格结构依据
- 估值质量依据
- 经营质量依据

禁止：

- 跨维度综合加权总分；
- 全市场 Top N；
- 每组机械 Top1 / Top2；
- 为了减少数量而强行判定支配；
- 单指标一票淘汰；
- 从全部候选里随意抽几只直接开始 Deep Research。

---

## 8. 第二阶段：结构化公司预筛

第一阶段未被明确支配者进入 `company_research_view`。

这一阶段**不访问互联网**，目标不是形成投资结论，而是回答：

> **仅根据已经准备好的公司级确定性事实，这家公司是否已经明显不值得占用昂贵 Deep Research 预算？**

### 8.1 输入事实

主要包括：

- 最近财报期；
- 当前价格结构摘要；
- PE-TTM / 动态 PE / PB / ROE；
- 营收同比；
- 净利润同比；
- 扣非 EPS 同比；
- 经营现金流 / 股；
- 毛利率；
- 净利润；
- 行业趋势 / 强度 / breadth；
- 程序机械关系标签：
  - 收入与利润方向是否背离；
  - 净利润与扣非方向是否背离；
  - 利润增长但经营现金流 / 股为负；
  - 收入和利润是否同时负增长；
  - 利润和扣非是否同时负增长；
  - 经营现金流 / 股是否为负；
  - 核心财务字段缺失数量。

若仓库当前没有可靠主营描述或盈利驱动结构化字段：

- `business_description` / `profit_driver` 保持空；
- 不得从行业名称猜主营或利润来源；
- 缺少这两个静态字段本身不意味着公司必须进入 Deep Research。

### 8.2 第二阶段只有三种结果

#### `CLEARLY_WEAK`

只有当结构化事实已经显示**多个独立方面明显偏弱**，且没有清晰的确定性反向优势时才使用。

典型情形包括但不限于：

- 收入和利润同时明显恶化，并且扣非也弱；
- 表面利润增长但扣非 / 现金流明显背离，且估值并未提供清晰安全垫；
- 盈利能力、增长和估值组合明显缺乏吸引力，且没有价格结构或经营数据上的明显补偿；
- 多个财务质量信号同时指向恶化。

这不是机械“一项触发即淘汰”。单个负面指标不允许形成 `CLEARLY_WEAK`。

#### `PASS_TO_DEEP_RESEARCH`

结构化事实具备继续研究价值，值得花公开资料研究预算。

#### `UNCERTAIN`

存在以下情况之一：

- 周期行业导致当前利润或估值可能失真；
- 数据互相冲突；
- 业务异质性使数字不能直接解释；
- 缺失的信息确实会改变结论；
- 无法仅凭结构化事实可靠判断。

`PASS_TO_DEEP_RESEARCH` 与 `UNCERTAIN` 都进入第三阶段。

### 8.3 第二阶段禁止事项

禁止：

- 联网查101家公司；
- 综合总分；
- 固定 Top N；
- 为了压到20或30只而调阈值；
- 单一 PE / ROE / 利润增长指标直接淘汰；
- 找到几只好公司后停止预筛直接发布榜单。

第二阶段应该是一遍低成本、结构化的公司级判断。

---

## 9. 第三阶段：Deep Research

只有第二阶段的：

- `PASS_TO_DEEP_RESEARCH`
- `UNCERTAIN`

进入真正公开资料研究。

第三阶段确认：

1. 真实主营与主要产品 / 业务；
2. 未来 1–2 个季度核心盈利驱动；
3. 主要收入和利润来源；
4. 行业改善是否真实传导到公司；
5. 核心 / 扣非利润与净利润方向是否一致；
6. 收入、毛利率、现金流、订单、销量、价格等是否支持利润变化；
7. 是否存在一次性收益、周期高点或其他估值扭曲；
8. 至少一条最可能推翻当前判断的反向证据。

如果申万三级行业内公司实际不可比，应在这一阶段按真实主营 + 盈利驱动重新理解可比关系。

单公司资料不足只影响该公司，标记为 `research_uncertain` 或 `waiting`，不得阻断其他幸存候选。

---

## 10. 最终估值与安全边际

最终安全区只能在 Deep Research 后形成。

每家公司尽量形成：

- `reasonable_price_range`
- `base_fair_value`
- `low_risk_buy_range`
- `conservative_upside`
- `downside_to_safety_zone`
- `hard_risk_boundary`（能可靠定义时）

最终安全边际综合：

- 正常化盈利对应的合理估值低位；
- PE / PB 与 ROE、增长、现金流匹配；
- 重要支撑；
- 前期重要低点；
- 成交密集区；
- 多种价值与价格因素重合区域。

> **程序结构硬筛只说明“值得研究”，不能直接复制成最终安全区。**

原则上优先当前价距离最终安全区域约 5% 以内的公司；距离明显过远进入等待池。

强周期公司必须使用正常化盈利，禁止用高景气期利润直接外推。

---

## 11. 向上空间

只有最终安全边际基本成立后，才比较向上空间。

保守目标区域综合：

- 正常化合理估值；
- 盈利修复能够支持的价值区间；
- 历史正常价格区间；
- 中期重要价格平台；
- 行业盈利逻辑未来 1–2 个季度的可验证性。

原则上：

- 保守上行空间 `>= 15%` 才具有较强吸引力；
- 不得用乐观目标价强行制造上行空间；
- 最近阻力只是短期压力，不直接等于全部上涨空间。

---

## 12. 趋势与市场风险

趋势只回答“什么时候参与”，不回答“是否值得研究”。

因此：

- `transition` 不得直接淘汰；
- `bearish` 不得单独淘汰；
- 接近压力位可以降低当前参与优先级；
- invalidation 是风险参考，不是全局 Gate。

市场 `high risk` 可以让最终推荐更保守，但不得：

- 改变程序候选全集；
- 跳过同行比较；
- 跳过结构化公司预筛；
- 成为“只研究几只最稳公司”的理由。

---

## 13. 最终状态与排序

公司最终进入：

- `confirmed`
- `waiting`
- `research_uncertain`
- `excluded`

通过公司确认后，正式优先级：

> **最终安全边际 → 保守上行空间 → 基本面稳定性 → 参与时机**

正式榜最多展示 10 只，不得凑数，允许空榜。

最终排名不能反向影响前面的研究范围。

---

## 14. 审计漏斗

最终至少记录：

- `snapshot.trade_date`
- `source_candidate_count`
- `structural_relevance_count`
- `peer_group_count`
- `peer_dominated_count`
- `company_prescreen_count`
- `company_clearly_weak_count`
- `deep_research_candidate_count`
- `company_confirmed_count`
- `research_uncertain_count`
- `waiting_count`
- `final_recommendation_count`

这些数字用于解释本轮漏斗，不创建复杂 Completion Gate。

---

## 15. 最终原则

> **不要让模型对上百家公司逐只联网研究。**

> **第一阶段只解决同行支配。**

> **第二阶段只做结构化公司预筛，不联网。**

> **Deep Research 是最后的昂贵验证层。**

> **程序消化确定性复杂度，模型消化真正需要解释和判断的复杂度。**

# A股低风险买点榜

## 1. 核心目标

寻找：

> **基本面没有明显恶化，当前价格经过价值与价格结构双重验证后具备安全边际，向下剩余空间有限，而未来 1–2 个季度保守上行空间充足的 A 股公司。**

核心原则：

> **先看还能跌多少，再看能涨多少。**

本榜单寻找的不是走势最强、公司最优秀或最早转强的股票，而是当前价格下风险收益最不对称的股票。

---

## 2. 程序与模型的职责边界

### 程序负责确定性工作

程序已经完成：

- 全市场数据完整性校验；
- 机械风险粗筛；
- 支撑距离、支撑触碰次数计算；
- 成交密集区距离、成交占比计算；
- 60 日价格位置计算；
- 结构硬筛；
- 申万三级行业映射；
- 将结构合格候选整理成 `candidates.json`；
- 再按申万三级行业生成 `peer_groups.json`，把第一阶段真正需要比较的价格结构、估值和经营事实放到同一个同行组里。

程序不做：

- 综合评分；
- Top N；
- 每组 Top1 / Top2；
- 同行支配结论；
- 最终投资结论。

### 当前结构硬筛

#### 深低位：`position_pct <= 20%`

至少满足一种高质量承接：

- strong support：距 `support_center <= 3%`，且 `support_touches >= 3`；
- strong volume zone：距 `volume_zone_center <= 3%`，且 `volume_zone_share_pct >= 12%`。

#### 中低位：`20% < position_pct <= 35%`

必须同时：

- 距 `support_center <= 5%`；
- 距 `volume_zone_center <= 5%`。

`position_pct > 35%` 不进入 model-ready 候选。

这些规则只回答：

> **当前价格结构是否值得占用模型研究预算。**

它不是最终 `low_risk_buy_range`。

### 模型真正负责什么

模型分两阶段工作。

**第一阶段只做同行支配判断：**

> **同一个申万三级行业组里，有没有某家公司已经被另一家公司明显支配，以至于没有必要优先进入公开 Deep Research？**

第一阶段不做长篇公司研究，不算最终目标价，不形成正式榜单。

**第二阶段才做公司研究：**

对第一阶段未被明确支配的候选，研究真实主营、盈利驱动、利润来源、周期位置、盈利质量、正常化估值、最终安全区和保守上行空间。

> **能用程序整理的事实，不交给模型重复劳动；模型只处理事实之间的经济含义与不可机械判断的权衡。**

---

## 3. 正式输入

正式运行使用：

- `data/runtime/meta.json`
- `meta.peer_group_file`：第一阶段同行比较视图
- `meta.candidate_file`：第二阶段的完整确定性背景表，需要时读取对应候选，不要求第一阶段重新完整扫描
- `skill/RUNTIME_READ_PROTOCOL.md`
- `skill/SKILL.md`

不再读取：

- `data/runtime/details/{code}.json`
- `data/runtime/screening_snapshot.json`
- `data/runtime/industry_state_compact.json`

`peer_groups.json` 不是新的筛选层。它只是把与第一阶段有关的原始事实按同行提前摆好，候选股票全集与 `candidates.json` 必须完全一致。

---

## 4. 正式研究流程

```text
717 机械候选
  ↓
程序结构硬筛
  ↓
model-ready candidates
  ↓
程序生成 peer_groups.json
  ↓
模型第一阶段：逐同行组轻量判断
  ├─ 单只组 → 直接进入 research candidates
  └─ 多只组 → 只判断 CLEARLY_DOMINATED / NOT_CLEARLY_DOMINATED
  ↓
未被明确支配者
  ↓
公开资料 Deep Research
  ↓
真实主营 / 盈利驱动 / 利润来源 / 周期位置
  ↓
正常化估值 + 价格结构
  ↓
最终 low_risk_buy_range
  ↓
正式榜 / waiting / research_uncertain / excluded
```

第一阶段的工作单位是**行业组**，不是从全体候选里自由挑选股票。

不得先随意挑几家公司做 Deep Research，再停止同行比较并发布榜单。

---

## 5. 第一阶段：同行组轻量比较

### 5.1 单只候选组

如果某申万三级行业组只有 1 只候选：

- 不存在同组同行可以形成明确支配；
- 不需要为了“比较”而额外推理；
- 该公司直接进入 research candidates。

### 5.2 多只候选组

只比较三类已经由程序整理好的事实。

#### A. 价格结构

主要看：

- `position_pct`
- `support_distance_pct`
- `support_touches`
- `volume_zone_distance_pct`
- `volume_zone_share_pct`
- `resistance_center`
- invalidation

这些候选已经通过结构硬筛。第一阶段比较的是**相对结构质量**，不是重新判定谁是否符合硬筛。

#### B. 估值质量

联合看：

- PE-TTM
- 动态 PE
- PB
- ROE
- 盈利增长

不得孤立比较 PE / PB。低 PE 可能来自周期盈利高点；较高 PB 如果对应更高且可持续的 ROE，也不能机械认定更差。

#### C. 经营质量

主要看：

- 营收同比
- 净利润同比
- 扣非 EPS 同比
- 经营现金流 / 股
- 毛利率

第一阶段只回答：

> **同组内是否存在明确支配关系？**

不是选“最好公司”，也不是给所有公司排序。

---

## 6. 明确支配规则

候选 A 只有在存在同组候选 B 且同时满足以下条件时，才允许在公开 Deep Research 前排除：

1. B 在价格结构、估值质量、经营质量三个维度中没有一个维度明显弱于 A；
2. B 至少在其中一个维度明显优于 A；
3. A 不存在 B 无法覆盖的明显差异化优势；
4. 不存在业务异质性、周期失真或数据冲突，需要公开研究才能解决。

第一阶段只允许两个方向：

- `CLEARLY_DOMINATED`
- `NOT_CLEARLY_DOMINATED`

只要有明显权衡、不可比性或不确定性，就归入 `NOT_CLEARLY_DOMINATED`，继续研究。

禁止：

- 跨维度加权总分；
- 全市场 Top N；
- 每组机械 Top1 / Top2；
- 为了减少研究数量而强行判定支配；
- 用行业强弱、趋势、PE、PB、ROE、利润增速中的单一指标一票淘汰；
- 从全部候选中凭感觉抽几只直接进入 Deep Research。

如果判定 `CLEARLY_DOMINATED`，至少说明：

- `dominated_by`
- 价格结构依据
- 估值质量依据
- 经营质量依据

---

## 7. Deep Research

只对 `NOT_CLEARLY_DOMINATED` 和单只组候选做公司级公开研究。

必要时从 `candidate_file` 读取对应候选的完整确定性字段，但不需要为了研究少量幸存者重新完整扫描整个 candidate 表。

公开资料确认：

1. 真实主营与主要产品 / 业务；
2. 未来 1–2 个季度核心盈利驱动；
3. 主要收入和利润来源；
4. 行业改善是否真实传导到公司；
5. 核心 / 扣非利润与净利润方向是否一致；
6. 收入、毛利率、现金流、订单、销量、价格等是否支持利润变化；
7. 是否存在一次性收益、周期高点或其他估值扭曲；
8. 至少一条最可能推翻当前判断的反向证据。

如果同一申万三级行业里的公司实际业务不可比，应在这一阶段按真实主营 + 盈利驱动重新理解可比关系，而不是在第一阶段为了淘汰而强行比较。

单公司研究失败只影响该公司，标记为 `research_uncertain` 或 `waiting`，不得阻断其他候选。

---

## 8. 最终估值与安全边际

最终安全区只能在 Deep Research 后形成。

每家公司尽量形成：

- `reasonable_price_range`
- `base_fair_value`
- `low_risk_buy_range`
- `conservative_upside`
- `downside_to_safety_zone`
- `hard_risk_boundary`（能够可靠定义时）

最终安全边际综合：

- 正常化盈利对应的合理估值低位；
- PE / PB 与 ROE、增长、现金流的匹配；
- 重要支撑；
- 前期重要低点；
- 成交密集区；
- 多种价值与价格因素重合区域。

> **程序结构硬筛只说明“值得研究”，不能直接生成最终安全区。**

原则上优先当前价距离最终安全区域约 5% 以内的公司；距离明显过远进入等待池。

强周期公司必须使用正常化盈利，禁止用高景气期利润直接外推。

---

## 9. 向上空间

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

## 10. 趋势与市场风险

趋势只回答“什么时候参与”，不回答“是否值得研究”。

因此：

- `transition` 不得直接淘汰；
- `bearish` 不得单独淘汰；
- 高位、短期大涨、接近压力位可以降低当前参与优先级；
- `invalidation` 是风险参考，不是全局 Gate。

市场 `high risk` 可以让最终推荐更保守，但不得改变程序候选全集，也不得成为跳过同行组的理由。

---

## 11. 公司状态与最终排序

每家公司最终进入：

- `confirmed`
- `waiting`
- `research_uncertain`
- `excluded`

通过公司确认后，正式优先级为：

> **最终安全边际 → 保守上行空间 → 基本面稳定性 → 参与时机**

正式榜最多展示 10 只，不得凑数，允许空榜。

---

## 12. 审计

最终至少记录：

- `snapshot.trade_date`
- `source_candidate_count`
- `structural_relevance_count`
- `peer_dominated_count`
- `research_candidate_count`
- `company_confirmed_count`
- `research_uncertain_count`
- `waiting_count`
- `final_recommendation_count`

程序还提供：

- `peer_group_count`
- `peer_group_singleton_count`
- `peer_group_max_size`

这些用于理解本轮模型实际面对的是多少个同行比较问题，不是额外筛选门槛。

---

## 13. 最终原则

> **程序负责把 109 只之类的大候选集合整理成少量同行比较问题；模型不再承担“从大表中自己挑谁值得看”的任务。**

> **第一阶段只判断明确支配；第二阶段才做真正公司研究。**

> **程序消化确定性复杂度，模型只处理真正需要判断的复杂度。**

> **市场风险影响最终行动，不影响同行比较规则。**

> **局部问题只局部降级，不阻断整轮。**

# A股低风险买点榜：运行时读取协议

> 本文件只约束版本锁定、runtime 信任边界、正式输入和任务级阻断条件。同行比较、公司预筛、Deep Research、估值、买点与排名规则，以同一锁定提交下的 `skill/SKILL.md` 为准。

## 1. 核心原则

> **不要要求模型对上百家公司逐只联网研究。程序先整理确定性事实，模型先做低成本判断，真正 Deep Research 只留给少量仍值得验证的公司。**

不建立复杂状态机或逐股票 completion gate。

---

## 2. 每轮版本锁定

每次定时触发、手动触发或用户明确要求重新执行，都视为新 run：

1. 获取 `xwan008/a-market-data` 当前 `main` commit SHA，记为 `locked_sha`；
2. 从同一 `locked_sha` 读取：
   - `skill/RUNTIME_READ_PROTOCOL.md`
   - `skill/SKILL.md`
   - `data/runtime/meta.json`
   - `meta.peer_group_file`
   - `meta.company_research_file`
   - `meta.candidate_file`（仅在最终 Deep Research / 估值需要更完整确定性字段时按需使用）
3. 同一 run 中禁止混用不同 SHA；
4. 禁止把上一轮同行判断、公司预筛或研究结论直接当成本轮事实。

---

## 3. 正式 runtime 输入

正式模型输入分层使用：

- `meta.peer_group_file`：第一阶段同行比较；
- `meta.company_research_file`：第二阶段结构化公司预筛；
- `meta.candidate_file`：第三阶段少量幸存者的完整确定性背景；
- `meta.json`、`SKILL.md`、本协议：全程规则与元数据。

不再读取或要求存在：

- `data/runtime/details/`
- `data/runtime/screening_snapshot.json`
- `data/runtime/industry_state_compact.json`

底层 snapshot、K 线、shards、行业状态仍由生成程序使用，不属于模型正式运行输入。

---

## 4. runtime 生成侧信任边界

`meta.runtime_validation.status == "passed"` 代表生成侧已经确定性验证：

- 机械候选代码唯一；
- `source_candidate_count` 与 snapshot 一致；
- model-ready candidates 满足正式结构硬筛；
- `candidate_count == structural_relevance_count`；
- candidate 表交易日与 columns 正确；
- peer group view 与 candidate 股票全集完全一致、无重复；
- company research view 与 candidate 股票全集完全一致、无重复；
- 三份 runtime 数据交易日一致；
- `peer_group_validation.status == "passed"`；
- `company_research_validation.status == "passed"`。

peer view 和 company research view 只改变确定性事实的组织方式，不自行评分、排名或做最终投资结论。

---

## 5. 当前结构硬筛语义

### 深低位：`position_pct <= 20%`

至少存在一种高质量承接：

- strong support：距 support center `<= 3%` 且 `support_touches >= 3`；
- strong volume zone：距 volume-zone center `<= 3%` 且 `volume_zone_share_pct >= 12%`。

### 中低位：`20% < position_pct <= 35%`

必须同时：

- 距 support center `<= 5%`；
- 距 volume-zone center `<= 5%`。

`position_pct > 35%` 不进入 model-ready candidates。

模型不得重新逐只计算或推翻这些程序硬规则。

---

## 6. Runtime Hard Gate

只有以下情况允许终止整轮任务：

- 当前应使用的正式 runtime 缺失或明显过期；
- `runtime_validation.status != "passed"`；
- snapshot 交易日与最近有效 A 股正式收盘不一致；
- `meta.json`、`peer_group_file`、`company_research_file` 或 `candidate_file` 无法读取；
- 三份 runtime 数据无法可靠解析；
- peer / company research view 与 candidate 表的交易日或股票全集明显冲突；
- peer / company research validation 未通过；
- 同一 run 无法维持单一 `locked_sha`。

候选表允许为空；程序硬筛后没有公司通过，不代表 runtime 失败。

---

## 7. 第一阶段：同行组轻量比较

第一阶段只读取 `peer_group_file`。

程序已经把全部 model-ready candidates 按申万三级行业分组，并整理：

- 价格结构事实；
- PE / PB / ROE 等估值事实；
- 收入 / 利润 / 扣非 / 现金流 / 毛利率等经营事实；
- 行业背景。

工作单位是**行业组**：

- 单只组：直接进入第二阶段；
- 多只组：只判断 `CLEARLY_DOMINATED` / `NOT_CLEARLY_DOMINATED`。

如果存在明显权衡、不可比性或不确定性，就保留为 `NOT_CLEARLY_DOMINATED`。

第一阶段禁止：长篇联网研究、全市场排序、综合加权评分、Top N、每组 Top1/Top2、找到几只好公司后直接发布。

---

## 8. 第二阶段：结构化公司预筛

第一阶段未被明确支配者进入第二阶段。

第二阶段主要读取 `company_research_file`，**不联网**。该视图已经把每家公司的确定性事实压缩在一行，包括：

- 当前价格结构摘要；
- PE-TTM / 动态 PE / PB / ROE；
- 营收、净利润、扣非 EPS、经营现金流、毛利率、净利润；
- 行业状态；
- 最近财报期；
- 程序可100%计算的质量背离标签，例如利润与扣非方向背离、利润增长但经营现金流为负、收入与利润方向背离；
- 若仓库存在可靠主营 / 盈利驱动结构化字段则提供；没有可靠来源时显式留空，不得从行业名称猜测。

模型在这一阶段只输出三种方向：

- `CLEARLY_WEAK`：结构化事实已经显示多个独立维度明显偏弱，且没有足以抵消的确定性优势，没有必要占用公开 Deep Research 预算；
- `PASS_TO_DEEP_RESEARCH`：结构化事实具备继续验证价值；
- `UNCERTAIN`：数据冲突、周期性、业务异质性或缺失信息使结构化事实不足以下结论。

`PASS_TO_DEEP_RESEARCH` 与 `UNCERTAIN` 都进入第三阶段。

这里不是 Top N，也不要求压到固定数量。拿不准就保留；但不能把“没有逐只联网研究”误认为研究未完成，因为第二阶段的目标本来就是低成本预筛。

---

## 9. 第三阶段：真正 Deep Research

只有第二阶段的 `PASS_TO_DEEP_RESEARCH` / `UNCERTAIN` 才进入公开资料研究。

这一阶段才允许：

- 按需读取 candidate 表中对应幸存者的完整确定性字段；
- 查询最新可靠公开资料；
- 确认真实主营、核心盈利驱动、主要利润来源；
- 判断一次性收益、周期高点、盈利质量与未来 1–2 个季度逻辑；
- 形成正常化估值、最终安全区、上下行空间与推翻条件。

**不得再要求对第二阶段已经判定 `CLEARLY_WEAK` 的公司逐只联网。**

单公司公开资料不足只影响该公司，进入 `research_uncertain` 或 `waiting`，不得阻断其他幸存者。

---

## 10. 市场风险

市场 `bearish / weak breadth / high risk` 只能影响最终行动：

- 更保守的正常化估值；
- 更强调最终安全边际；
- 更倾向等待；
- 正式榜可以减少甚至为空。

市场风险不得改变程序候选全集，也不得成为跳过第一、第二阶段的理由。

---

## 11. 收盘版流程

```text
锁定 SHA
→ Runtime Hard Gate
→ peer_groups：同行轻比较
→ company_research_view：结构化公司预筛（不联网）
→ PASS / UNCERTAIN 幸存者
→ 少量公开 Deep Research
→ 正常化估值 + 最终安全区
→ 正式榜 / waiting / uncertain / excluded
```

早间隔夜版仍需锁定当前 main，可以上一有效收盘研究结论为基准，只复核真正可能改变公司逻辑、估值、安全区或重大风险的隔夜信息。

---

## 12. 审计

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

这些统计用于解释漏斗，不创建复杂 Completion Gate。

---

## 13. 最终原则

> **同行比较不是公司研究。**

> **结构化公司预筛不是 Deep Research。**

> **Deep Research 是最后的昂贵验证层，不是对上百家公司逐只进行的批量筛选层。**

> **程序消化确定性复杂度，模型只处理真正需要判断的复杂度。**

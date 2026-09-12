# A股低风险买点榜：运行时读取协议

> 本文件只约束版本锁定、runtime 信任边界、正式输入和阶段执行边界。同行比较、公司预筛、Deep Research、估值、买点与排名规则，以同一锁定提交下的 `skill/SKILL.md` 为准。

## 1. 核心原则

> **不要要求模型对上百家公司逐只联网研究。程序先整理确定性事实，模型先做低成本判断，真正 Deep Research 只留给少量仍值得验证的公司。**

不建立复杂状态机或逐股票 completion gate。

但必须存在一个简单、明确的阶段边界：

> **第二阶段完整 Prescreen Ledger 未冻结之前，第三阶段 Web Research 不得开始。**

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
   - `meta.candidate_file`（仅在第三阶段少量幸存者需要更完整确定性字段时按需使用）
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

程序已经把全部 model-ready candidates 按申万三级行业分组，并整理价格结构、估值、经营和行业背景事实。

工作单位是**行业组**：

- 单只组：直接进入第二阶段；
- 多只组：只判断 `CLEARLY_DOMINATED` / `NOT_CLEARLY_DOMINATED`。

如果存在明显权衡、不可比性或不确定性，就保留为 `NOT_CLEARLY_DOMINATED`。

第一阶段禁止：长篇联网研究、全市场排序、综合加权评分、Top N、每组 Top1/Top2、找到几只好公司后直接发布。

---

## 8. 第二阶段：结构化公司预筛

第一阶段未被明确支配者进入第二阶段。

第二阶段主要读取 `company_research_file`，**禁止联网**。该视图已经把每家公司的确定性事实压缩在一行，包括：

- 当前价格结构摘要；
- PE-TTM / 动态 PE / PB / ROE；
- 营收、净利润、扣非 EPS、经营现金流、毛利率、净利润；
- 行业状态；
- 最近财报期；
- 程序可100%计算的质量背离标签；
- 若仓库存在可靠主营 / 盈利驱动结构化字段则提供；没有可靠来源时显式留空，不得从行业名称猜测。

模型在这一阶段只输出：

- `CLEARLY_WEAK`
- `PASS_TO_DEEP_RESEARCH`
- `UNCERTAIN`

拿不准就 `UNCERTAIN`，而不是为了减少数量强行淘汰。

### 第二阶段必须先生成完整 Prescreen Ledger

在任何 Web 查询前，必须先对**全部第二阶段输入股票**生成紧凑 Ledger：

```text
code | result | reason_code
```

然后一次性形成并冻结：

- `prescreen_input_codes`
- `clearly_weak_codes`
- `pass_to_deep_research_codes`
- `uncertain_codes`
- `deep_read_codes = pass_to_deep_research_codes ∪ uncertain_codes`

要求：

1. 每个 `prescreen_input_code` 恰好出现一次；
2. 三分类集合互斥；
3. 三分类集合并集等于 `prescreen_input_codes`；
4. 先统计三类数量，再进入第三阶段；
5. **在 `deep_read_codes` 冻结前，不得发出任何公司级 Web 查询。**

这是一个简单的阶段产物，不是复杂 Completion Gate。

---

## 9. 第三阶段：真正 Deep Research

第三阶段的唯一研究集合是已经冻结的 `deep_read_codes`。

不得在第三阶段重新从公司池里自由挑选，也不得把实际搜索过的公司反向当成“本应研究集合”。

这一阶段才允许：

- 按需读取 candidate 表中对应幸存者的完整确定性字段；
- 查询最新可靠公开资料；
- 确认真实主营、核心盈利驱动、主要利润来源；
- 判断一次性收益、周期高点、盈利质量与未来 1–2 个季度逻辑；
- 形成正常化估值、最终安全区、上下行空间与推翻条件。

同时维护：

- `actual_researched_codes`

只有完成足以形成公司级研究状态的公开资料核验，才计入该集合。搜索请求次数不等于研究完成数。

单公司公开资料不足只影响该公司，进入 `research_uncertain` 或 `waiting`，不得阻断其他幸存者。

---

## 10. Deep Research 覆盖审计

第三阶段结束时必须比较：

```text
expected_deep_research_codes = deep_read_codes
actual_deep_researched_codes = actual_researched_codes
```

若集合完全相等：

> `Deep Research coverage = COMPLETE`

若不相等：

> `Deep Research coverage = INCOMPLETE`

并列出：

- `missing_deep_research_codes`
- `unexpected_researched_codes`（如有）

如果本轮没有先生成完整 Prescreen Ledger，或者无法恢复 `deep_read_codes`，则必须标记：

> `Deep Research coverage = UNVERIFIED`

不得把“实际搜索覆盖25只”等事实冒充“按规则本应进入 Deep Research 的就是25只”。

这只是集合审计，不引入复杂状态机。

---

## 11. 市场风险

市场 `bearish / weak breadth / high risk` 只能影响最终行动：

- 更保守的正常化估值；
- 更强调最终安全边际；
- 更倾向等待；
- 正式榜可以减少甚至为空。

市场风险不得改变程序候选全集，也不得成为跳过第一、第二阶段的理由。

---

## 12. 收盘版流程

```text
锁定 SHA
→ Runtime Hard Gate
→ peer_groups：同行轻比较
→ company_research_view：结构化公司预筛（禁止联网）
→ 完整 Prescreen Ledger
→ 冻结 deep_read_codes
→ 只对 deep_read_codes 做公开 Deep Research
→ 比较 expected vs actual researched codes
→ 正常化估值 + 最终安全区
→ 正式榜 / waiting / uncertain / excluded
```

早间隔夜版仍需锁定当前 main，可以上一有效收盘研究结论为基准，只复核真正可能改变公司逻辑、估值、安全区或重大风险的隔夜信息。

---

## 13. 审计

最终至少记录：

- `snapshot.trade_date`
- `source_candidate_count`
- `structural_relevance_count`
- `peer_group_count`
- `peer_dominated_count`
- `company_prescreen_count`
- `company_clearly_weak_count`
- `pass_to_deep_research_count`
- `uncertain_prescreen_count`
- `deep_research_candidate_count`
- `actual_deep_researched_count`
- `company_confirmed_count`
- `research_uncertain_count`
- `waiting_count`
- `final_recommendation_count`

并保留：

- `clearly_weak_codes`
- `pass_to_deep_research_codes`
- `uncertain_codes`
- `deep_read_codes`
- `actual_researched_codes`

这些统计用于解释漏斗，不创建复杂 Completion Gate。

---

## 14. 最终原则

> **同行比较不是公司研究。**

> **结构化公司预筛不是 Deep Research。**

> **第二阶段必须先完整冻结 Prescreen Ledger，不能边预筛边联网。**

> **Deep Research 的应研究集合来自 Ledger，不来自实际搜索记录。**

> **Deep Research 是最后的昂贵验证层，不是对上百家公司逐只进行的批量筛选层。**

> **程序消化确定性复杂度，模型只处理真正需要判断的复杂度。**
# A股低风险买点榜：运行时读取协议

> 本文件只约束版本锁定、runtime 信任边界、正式输入和任务级阻断条件。同行比较、公司研究、估值、买点与排名规则，以同一锁定提交下的 `skill/SKILL.md` 为准。

## 1. 核心原则

> **程序先把确定性筛选和同行事实整理完成；模型第一阶段处理同行组，第二阶段才研究公司。**

不建立额外的复杂状态机或逐股票 completion gate。

---

## 2. 每轮版本锁定

每次定时触发、手动触发或用户明确要求重新执行，都视为新 run：

1. 获取 `xwan008/a-market-data` 当前 `main` commit SHA，记为 `locked_sha`；
2. 从同一 `locked_sha` 读取：
   - `skill/RUNTIME_READ_PROTOCOL.md`
   - `skill/SKILL.md`
   - `data/runtime/meta.json`
   - `meta.peer_group_file`
   - `meta.candidate_file`（只作为第二阶段完整确定性背景表）
3. 同一 run 中禁止混用不同 SHA；
4. 禁止把上一轮候选、同行比较或公司研究结论直接当成本轮事实。

---

## 3. 正式 runtime 输入

正式模型输入为：

- `data/runtime/meta.json`
- `meta.peer_group_file`：第一阶段主要输入
- `meta.candidate_file`：第二阶段按需使用的完整候选背景表
- `skill/RUNTIME_READ_PROTOCOL.md`
- `skill/SKILL.md`

不再读取或要求存在：

- `data/runtime/details/`
- `data/runtime/screening_snapshot.json`
- `data/runtime/industry_state_compact.json`

底层 snapshot、K 线、shards、行业状态等仍由生成程序使用，但不属于模型正式运行输入。

---

## 4. runtime 生成侧信任边界

`meta.runtime_validation.status == "passed"` 代表生成侧已经确定性验证：

- snapshot 机械候选代码唯一；
- `source_candidate_count` 与 snapshot 候选数一致；
- 所有机械候选行业映射完整；
- model-ready candidate 表每一行满足正式结构硬筛；
- `candidate_count == structural_relevance_count`；
- candidate 表交易日和 columns 正确；
- `peer_group_file` 与 candidate 表交易日一致；
- peer view 中的股票代码无重复；
- peer view 股票全集与 candidate 表股票全集完全一致；
- `peer_group_validation.status == "passed"`。

peer view 只改变模型看到事实的组织方式，不增加新的股票筛选。

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
- snapshot 交易日与当前应使用的最近有效 A 股正式收盘不一致；
- `meta.json`、`peer_group_file` 或 `candidate_file` 无法读取；
- peer view 或 candidate 表无法可靠解析；
- peer view 与 candidate 表交易日、候选全集或 meta 明显冲突；
- `peer_group_validation.status != "passed"`；
- 同一 run 无法维持单一 `locked_sha`。

候选表允许为空；程序硬筛后没有公司通过，不代表 runtime 失败。

---

## 7. 第一阶段读取规则：peer groups

第一阶段以 `peer_group_file` 为主，不要求模型重新完整扫描 `candidate_file`。

程序已经把所有 model-ready candidates 按申万三级行业放入 group，并提供第一阶段所需的：

- 价格结构事实；
- PE / PB / ROE 等估值事实；
- 收入 / 利润 / 扣非 / 现金流 / 毛利率等经营事实；
- 行业背景字段。

模型以**一个行业组**为最小工作单位：

- 单只组：直接进入 research candidates；
- 多只组：只判断哪些公司 `CLEARLY_DOMINATED`，其余全部视为 `NOT_CLEARLY_DOMINATED`。

不得：

- 从所有股票里自由抽几只先研究；
- 在第一阶段进行长篇公开资料研究；
- 做全市场综合排序；
- 做 Top N 或每组 Top1 / Top2；
- 因市场风险高而跳过同行组；
- 因已经找到几只不错的公司而提前转入正式榜单。

如果某一组内无法可靠判断支配关系，就保留，而不是为了压缩数量强行淘汰。

---

## 8. 第二阶段读取规则：公司 Deep Research

第一阶段之后：

- `CLEARLY_DOMINATED` 不进入公开 Deep Research；
- 单只组与 `NOT_CLEARLY_DOMINATED` 进入 research candidates。

第二阶段才允许：

- 按需从 `candidate_file` 读取对应幸存候选的更完整确定性字段；
- 使用最新可靠公开资料确认主营、盈利驱动、利润来源、周期位置和盈利质量；
- 形成正常化估值与最终安全区。

不要求为了少量 research candidates 再完整扫描整张 candidate 表。

---

## 9. 不属于全局失败的情况

以下情况只影响对应公司：

- 公开资料不足；
- 主营或盈利驱动暂时无法可靠确认；
- 某项估值无法可靠形成；
- 某行业证据存在冲突；
- 某公司业务与三级行业实际不可比；
- 某公司存在一次性收益或周期高点疑问；
- 单个公开来源不可访问。

对应公司进入 `confirmed`、`waiting`、`research_uncertain` 或 `excluded`，不得因此阻断其他候选。

---

## 10. 市场风险的作用边界

市场 `bearish / weak breadth / high risk` 等状态只能影响最终行动层：

- 更保守地确认正常化估值；
- 更强调最终安全边际；
- 更倾向 `waiting` 而不是追价；
- 最终推荐数量可以减少甚至为空。

市场风险不得改变程序候选全集，也不得替代或缩小第一阶段同行比较。

---

## 11. 收盘版与早间增量版

### 收盘正式版

```text
锁定 SHA
→ meta / runtime Hard Gate
→ 读取 peer groups
→ 逐组轻量同行支配判断
→ research candidates
→ 按需读取 candidate 背景 + 公开 Deep Research
→ 正常化估值 + 最终安全区
→ 正式榜 / waiting / uncertain / excluded
```

### 早间隔夜增量版

仍需重新锁定当前 main 并读取当前 meta / Skill。

允许以上一有效收盘版的公司级结论为比较基准，只复核真正可能改变公司盈利逻辑、正常化估值、最终安全边际、保守上行空间或重大风险的隔夜信息。

早间版不重新执行已经由程序固化的结构硬筛计算。

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

meta 还直接提供：

- `peer_group_count`
- `peer_group_singleton_count`
- `peer_group_max_size`

只需要明确：

> `Runtime Hard Gate = PASS / FAIL`

这些统计用于解释本轮工作量，不创建新的复杂 Completion Gate。

---

## 13. 最终原则

> **第一阶段输入是程序已经整理好的同行问题，不是让模型面对一张大表自己挑股票。**

> **第二阶段才研究公司。**

> **程序消化确定性复杂度，模型消化认知复杂度。**

> **全局问题才全局停止，局部问题只局部降级。**

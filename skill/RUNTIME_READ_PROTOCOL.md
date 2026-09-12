# A股低风险买点榜：运行时读取协议

> 本文件只约束版本锁定、runtime 信任边界、正式输入和任务级阻断条件。选股、同行比较、公司研究、估值、买点与排名规则，以同一锁定提交下的 `skill/SKILL.md` 为准。

## 1. 核心原则

> **程序负责证明数据完整并完成确定性筛选；模型只读取已经准备好的候选表并做研究判断。**

必须区分：

1. **Runtime Hard Gate**：只有会系统性污染整份榜单的问题才允许终止任务；
2. **候选级不确定性**：单公司研究失败只影响该公司；
3. **审计指标**：用于解释研究覆盖，不作为额外 Gate。

---

## 2. 每轮版本锁定

每次定时触发、手动触发或用户明确要求重新执行，都视为新 run：

1. 获取 `xwan008/a-market-data` 当前 `main` commit SHA，记为 `locked_sha`；
2. 从同一 `locked_sha` 读取：
   - `skill/RUNTIME_READ_PROTOCOL.md`
   - `skill/SKILL.md`
   - `data/runtime/meta.json`
   - `meta.candidate_file`
3. 同一 run 中禁止混用不同 SHA；
4. 禁止把上一轮候选、同行比较或公司研究结论直接当成本轮事实。

---

## 3. 唯一正式 runtime 输入

正式模型输入只有：

- `data/runtime/meta.json`
- `meta.candidate_file` 指向的单一 model-ready 候选表
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
- model-ready 表每一行满足当前正式结构硬筛规则；
- `candidate_count == structural_relevance_count`；
- candidate 表交易日与 snapshot 一致；
- candidate 表 columns 与 meta 声明一致。

当前正式结构规则由 `meta.structural_rule` 与同一 SHA 下的 `SKILL.md` 共同说明。

模型不得重新逐只计算或推翻这些程序硬规则。

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

### 高位

`position_pct > 35%` 不进入 model-ready candidates。

这些只是程序化研究准入规则，不是最终安全区。

---

## 6. Runtime Hard Gate

只有以下情况允许终止整轮任务：

- 当前应使用的正式 runtime 缺失或明显过期；
- `runtime_validation.status != "passed"`；
- snapshot 交易日与当前应使用的最近有效 A 股正式收盘不一致；
- `meta.json` 或 `candidate_file` 无法读取；
- candidate 表无法可靠解析；
- candidate 表交易日、候选数、columns 与 meta 明显冲突；
- 同一 run 无法维持单一 `locked_sha`。

候选表允许为空；程序硬筛后没有公司通过，不代表 runtime 失败。

---

## 7. 候选表读取规则

模型必须完整消费 `candidate_file` 中全部 model-ready candidates。

候选表已经：

- 通过机械风险粗筛；
- 通过正式结构硬筛；
- 合并申万三级行业字段；
- 合并价格结构、估值和经营质量字段；
- 按行业代码与股票代码排序，便于同行比较。

因此模型不得：

- 回到原始机械候选重新筛选；
- 重算或修改深低位 / 中低位结构硬规则；
- 因市场风险高而只读候选表的一部分；
- 因已经找到足够多好公司而提前停止同行比较。

不再规定固定窗口、EOF 二次确认或逐 detail completion gate。若某次工具响应被截断，应换用能够取得完整 candidate 表的可靠读取方式。

---

## 8. 模型研究边界

候选表完整读取后，严格按 `SKILL.md` 执行：

1. 按申万三级行业做初始分组；
2. 比较价格结构 / 估值质量 / 经营质量；
3. 只有被同行明确支配的公司才允许在公开 Deep Research 前排除；
4. 其余候选使用最新可靠公开资料做公司级研究；
5. 最终安全区只能在公开 Deep Research 和正常化估值后形成。

公开资料用于验证公司，不得扩展程序生成的候选全集。

---

## 9. 不属于全局失败的情况

以下情况只影响对应公司：

- 某公司公开资料不足；
- 主营或盈利驱动暂时无法可靠确认；
- 某项估值无法可靠形成；
- 某行业证据存在冲突；
- 某公司业务与三级行业实际不可比；
- 某公司存在一次性收益或周期高点疑问；
- 单个网页或公开来源不可访问。

对应公司进入：

- `confirmed`
- `waiting`
- `research_uncertain`
- `excluded`

不得因此阻断其他候选和整轮发布。

---

## 10. 市场风险的作用边界

市场 `bearish / weak breadth / high risk` 等状态只能影响最终行动层：

- 更保守地确认正常化估值；
- 更强调最终安全边际；
- 更倾向 `waiting` 而不是追价；
- 最终推荐数量可以减少甚至为空。

市场风险不得：

- 改写程序生成的候选表；
- 缩小候选表研究覆盖；
- 替代同行三维比较；
- 作为“只研究少数最稳公司”的理由。

---

## 11. 收盘版与早间增量版

### 收盘正式版

```text
锁定 SHA
→ meta Hard Gate
→ 完整读取唯一 candidates 表
→ 同行三维比较
→ 公开 Deep Research
→ 正常化估值 + 最终安全区
→ 正式榜 / waiting / uncertain / excluded
```

### 早间隔夜增量版

仍需重新锁定当前 main 并读取当前 meta / Skill。

允许以上一有效收盘版的公司级结论为比较基准，只复核真正可能改变以下判断的隔夜信息：

- 公司 / 行业盈利逻辑；
- 正常化估值；
- 最终安全边际；
- 保守上行空间；
- 重大风险与推翻条件。

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

其中 `source_candidate_count` 与 `structural_relevance_count` 直接来自 meta，不由模型重新计算。

只需要明确：

> `Runtime Hard Gate = PASS / FAIL`

---

## 13. 最终原则

> **程序消化确定性复杂度，模型消化认知复杂度。**

> **一个候选表就是模型的正式数据入口。**

> **全局问题才全局停止，局部问题只局部降级。**

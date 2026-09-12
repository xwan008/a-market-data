# A股低风险买点榜：运行时读取与版本边界协议

> 本文件只约束“读哪一版数据、怎样完整读取运行时数据、何时允许进入下一阶段”。
> 对这些问题，本文件为任务级最高优先级协议；选股、研究、估值与排名规则仍以同一锁定 SHA 下的 `skill/SKILL.md` 为准。
>
> 当前协议版本：`screening_details_v3`。
> `SKILL.md` 中仍出现的 `candidate_shards_v2`、`candidate_files`、`completed_candidate_files`、必须全量读取全部候选 shard 等旧运行时条款，均视为 V2 兼容说明；在 V3 runtime 下由本文件替代。

## 1. 设计目标

V3 的核心原则：

> **全量轻读，少量深读。**

数据生成脚本负责确定性粗筛、结构压缩和全局一致性校验；模型负责不可机械化的判断。

正式运行不再要求模型读取全部候选公司的完整明细。运行时分成两层：

1. **Screening 层**：读取全部候选的轻量记录，用于快速初筛；
2. **Detail 层**：只读取模型选中的少量公司的完整 runtime 明细。

这不是降低数据完整性要求，而是把“全量一致性校验”前移到数据生成阶段，把“深度读取”限制在真正进入研究阶段的公司。

---

## 2. 新执行与同一 run 续读

### 新执行

每一次新的定时触发、手动触发或用户明确要求“重新执行一次任务”，都必须视为全新的 run：

1. 重新解析仓库 `xwan008/a-market-data` 当前 `main` commit SHA；
2. 记为 `locked_sha`；
3. 禁止复用上一轮 run 的 `locked_sha`、筛选结果或 detail 读取状态；
4. 从本轮 `locked_sha` 重新读取本文件、`skill/SKILL.md` 和 `data/runtime/meta.json`。

### 同一 run 续读

如果当前 run 尚未结束，只是继续同一轮执行：

- 保持原 `locked_sha`；
- 从当前阶段继续；
- 不重新解析 `main`；
- 不重复已完成且已校验的源文件窗口。

---

## 3. 版本与数据新鲜度

每轮开始顺序固定为：

1. 解析当前 `main` SHA，记为 `locked_sha`；
2. 从 `locked_sha` 读取：
   - `skill/RUNTIME_READ_PROTOCOL.md`
   - `skill/SKILL.md`
   - `data/runtime/meta.json`
3. `meta` 必须满足：
   - `schema_version == 3`
   - `runtime_format == "screening_details_v3"`
   - `runtime_validation.status == "passed"`
4. 根据 `meta.snapshot.trade_date`、`meta.snapshot.market_status` 与当前时点判断是否为当前应使用的最近有效收盘；
5. 数据新鲜度通过后，才进入 Screening 层。

非交易日允许沿用最近有效收盘数据。若当前正式收盘版理应已有更新交易日，但 runtime 仍停留在更早交易日，则不得发布新的正式榜单。

本轮后续所有仓库读取必须显式使用同一个 `locked_sha`。

---

## 4. V3 runtime 文件

V3 正式机械数据入口只有：

- `data/runtime/meta.json`
- `meta.industry_state_file`
- `meta.screening_file`
- `meta.detail_file_template` 指向的、**本轮被选中进入深读的股票 detail 文件**
- `skill/SKILL.md`

不得为了“完整”再去读取旧版 `candidates_*.json`。V3 runtime 中它们不是正式入口。

`data/snapshot.json` 继续作为数据生成源和兼容文件保留，正式运行不直接读取。

---

## 5. Screening / Industry 的列式轻量格式

为降低 Connector 返回体积，V3 的 `screening_file` 与 `industry_state_file` 不再为每条记录重复 JSON key，而采用：

```text
columns: ["field_a", "field_b", ...]
rows:
  ["value_a", "value_b", ...]
  ["value_a", "value_b", ...]
```

解释规则：

- `columns[i]` 是 `rows[*][i]` 的字段名；
- 每个 `row` 的长度必须等于 `len(columns)`；
- `screening_columns` 与 `industry_columns` 同时写入 `meta.json`，用于快速校验；
- 模型必须按 `columns` 映射字段，不得依赖固定数组下标猜字段；
- `detail_file` 不再重复存储在每条 screening row 中，应使用：
  `meta.detail_file_template.replace("{code}", code)` 构造。

这种格式只用于轻量 Screening / Industry 层。单股 detail 文件继续使用普通具名 JSON 对象。

---

## 6. 源文件窗口读取规则

不同文件使用不同默认窗口：

- `meta.json`：最多 250 行；
- 单股 detail：最多 250 行；
- `industry_state_file`：**默认最多 50 行**；
- `screening_file`：**默认最多 50 行**。

`screening_file` 必须按固定 50 行源窗口连续读取，例如：

- `1–50`
- `51–100`
- `101–150`
- ...

如果某个窗口仍触发响应截断、resource continuation 或返回过大：

1. 不把 response-resource continuation 当作正常读取路径；
2. 将**同一源文件、同一起始位置**缩小窗口，例如：
   - Screening：`50 → 25 → 10`
   - 其他文件：`250 → 100 → 50`
3. 重新读取该段；
4. 再继续后续连续源文件窗口。

不得跳行、重叠、倒退或根据内容猜测下一起始行。

---

## 7. EOF 判定

对于需要完整读取的每个 runtime 文件：

1. 按连续源文件窗口读取；
2. 即使当前窗口已经看到 JSON 结束括号，也不得仅凭视觉判断 EOF；
3. 必须请求下一个连续窗口；
4. 只有下一个窗口返回空内容，才确认真实 EOF；
5. 确认 EOF 后才做 JSON 和字段校验。

因此：

`JSON visually closed != confirmed EOF`

`next source window empty == confirmed EOF`

---

## 8. Build-time Runtime Validation

V3 将原本需要模型跨全部 shard 执行的全局一致性校验前移到数据生成脚本。

`meta.runtime_validation.status == "passed"` 必须代表生成阶段已经确定性验证：

- 候选代码唯一；
- `source_candidate_count` 与 snapshot 候选数一致；
- `screening_count == source_candidate_count`；
- `detail_count == screening_count`；
- 行业数与 snapshot 行业数一致；
- 每个候选 `industry_code` 均能映射到行业状态；
- 每个 screening candidate 均生成确定性的 detail 文件。

如果 `runtime_validation.status != "passed"`，不得进入正式研究。

模型不需要为了重新证明这些生成期不变量而读取全部 detail 文件。

---

## 9. Screening Completion Gate

进入模型初筛前，必须同时满足：

- `meta.schema_version == 3`
- `meta.runtime_format == screening_details_v3`
- `meta.runtime_validation.status == passed`
- `industry_state_file` 已确认真实 EOF 且可解析
- `screening_file` 已确认真实 EOF 且可解析

行业文件必须满足：

- `schema_version == 3`
- `trade_date == meta.snapshot.trade_date`
- `industry_count == len(rows) == meta.industry_count`
- `columns == meta.industry_columns`
- 每个 row 长度等于 `len(columns)`

Screening 文件必须满足：

- `schema_version == 3`
- `trade_date == meta.snapshot.trade_date`
- `source_candidate_count == meta.source_candidate_count`
- `screening_count == len(rows) == meta.screening_count`
- `columns == meta.screening_columns`
- 每个 row 长度等于 `len(columns)`
- `columns` 至少包含：
  `code / name / price / industry_code / pe_ttm / pe_dynamic / roe / revenue_yoy / net_profit_yoy / close_change_20d_pct / position_pct / trend_state / break_state / support_center / resistance_center / invalidation_price / invalidation_direction`

同时：

- 所有已读取文件来自同一 `locked_sha`
- 不存在待继续的 source window

通过后：

`screening_completion_gate == passed`

此时允许模型基于轻量字段进行第一轮筛选。

---

## 10. 模型初筛

Screening 层只用于缩小研究空间，不发布最终榜单。

模型根据：

- 行业状态
- 盈利增速
- 基础估值
- ROE
- 趋势状态
- 价格位置
- 支撑 / 压力 / 失效位
- 近 20 日涨幅与追高风险

将全部轻量候选压缩成一个 `deep_read_codes` 集合。

默认目标：

- 通常 `15–30` 只；
- 高风险市场可以更少；
- 只有在候选高度分散且确有必要时才超过 30；
- 不得为了“凑数量”扩大集合。

这一步只是研究资源分配，不等于最终推荐。

---

## 11. Detail 深读

对 `deep_read_codes` 中每只股票：

1. 从 `meta.detail_file_template` 用股票代码构造 detail 路径；
2. 从同一 `locked_sha` 读取；
3. 按本协议源文件窗口规则读到真实 EOF；
4. 校验：
   - `schema_version == 3`
   - `trade_date == meta.snapshot.trade_date`
   - `code` 与目标股票代码一致
   - `candidate` 为合法对象

未进入 `deep_read_codes` 的 detail 文件：

- 不要求读取；
- 不影响 Completion Gate；
- 不得因为“尚未读取全部 details”而阻止运行结束。

---

## 12. Deep Research Completion Gate

开始正式行业复核、同行择优、公司确认、估值和排名之前，必须满足：

- `screening_completion_gate == passed`
- `deep_read_codes` 已确定
- `completed_detail_files == len(deep_read_codes)`
- 实际完成 detail 代码集合与 `deep_read_codes` 完全一致
- 所有 detail 来自同一 `locked_sha`
- 不存在待继续的 source window

通过后：

`deep_research_completion_gate == passed`

只有此时才进入 `SKILL.md` 定义的正式研究流程。

---

## 13. `snapshot_read_incomplete` 的允许条件

只有以下情况才允许输出 `snapshot_read_incomplete`：

- V3 必需文件在锁定 SHA 下不存在；
- 固定源文件窗口经过缩窗重试仍无法取得所需源文件内容；
- 已确认 EOF 后 JSON 不合法；
- schema / trade_date / count / columns / row length 等校验失败；
- `meta.runtime_validation.status != passed`；
- Screening Completion Gate 失败；
- 被选中的 detail 文件缺失或校验失败；
- Deep Research Completion Gate 失败。

以下情况本身不是失败理由：

- 单次工具响应 `truncated`；
- response resource 出现 continuation；
- 已经进行了较多工具调用；
- 上下文较长；
- 还有大量**未被选中**的 detail 文件没有读取。

最后一条是 V3 与 V2 的关键区别。

---

## 14. 终止前强制检查

输出正式榜单前必须确认：

`pending_source_window == false`

`screening_completion_gate == passed`

`deep_research_completion_gate == passed`

`completed_detail_files == len(deep_read_codes)`

任一条件不满足时，不得发布正式榜单。

但**不得**再检查或要求：

`completed_detail_files == meta.detail_count`

因为 V3 明确禁止为了完整性而全量深读全部候选。

---

## 15. 核心原则

V2：

`全量候选 → 全量深读 → 再筛选`

V3：

`全量候选 → 轻量读取 → 模型初筛 → 少量深读 → 正式研究`

最终原则：

> **程序负责证明数据完整，模型负责分配研究注意力。**

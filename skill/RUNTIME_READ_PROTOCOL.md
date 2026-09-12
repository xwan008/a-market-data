# A股低风险买点榜：运行时读取与版本边界协议

> 本文件只约束“读哪一版数据、怎样完整读取运行时 JSON、何时允许结束读取”。
> 对这些问题，本文件为任务级最高优先级协议；选股、研究、估值与排名规则仍以同一锁定 SHA 下的 `skill/SKILL.md` 为准。

## 1. 新执行与断点续读必须严格区分

### 新执行
每一次新的定时触发、手动触发或用户明确要求“重新执行一次任务”，都必须视为一个全新的 run：

1. 从头解析仓库 `xwan008/a-market-data` 当下 `main` commit SHA；
2. 禁止复用上一轮 run 的 `locked_sha`；
3. 禁止因为上一轮已经读过某些 shard 而从中间继续；
4. 必须重新从本轮 `locked_sha` 读取规则、`meta.json`、行业状态与全部候选分片。

### 同一 run 的断点续读
只有当前这一次 run 尚未结束、只是同一轮读取过程需要继续时，才保持原 `locked_sha` 不变并从当前源文件的下一个未读取行继续。

任何新的 scheduled/manual invocation 都不是上一轮的续读。

---

## 2. 版本与数据新鲜度

每轮开始顺序固定为：

1. 解析当前 `main` SHA，记为 `locked_sha`；
2. 从 `locked_sha` 读取 `skill/SKILL.md`、本文件和 `data/runtime/meta.json`；
3. 根据 `meta.trade_date`、`meta.latest_valid_close_date`、`meta.market_status` 与当前时点判断数据是否对应当前应使用的最近有效收盘；
4. 只有数据新鲜度通过后，才继续读取行业状态与候选分片；
5. 本轮后续所有仓库读取都必须显式使用同一个 `locked_sha`。

注意：

- `main` 出现新的规则/文档提交，不等于市场数据已重新生成；
- 是否需要新 runtime，依据“当前时点最新有效交易日”判断，而不是依据文件是否刚刚产生新 commit；
- 非交易日允许沿用最近有效收盘数据；
- 若正式收盘版应当已有更新交易日数据，但 `meta` 仍旧停留在更早交易日，则输出数据过期/不完整状态，不得发布新的正式榜单。

---

## 3. Runtime JSON 禁止整文件首读

以下运行时 JSON 禁止使用整文件读取作为正常路径：

- `data/runtime/meta.json`；
- `meta.industry_state_file`；
- `meta.candidate_files` 中全部 `candidates_*.json`。

必须直接使用 GitHub 源文件行区间读取，并显式指定 `ref=locked_sha`。

默认窗口：每次最多 250 个源文件行。

固定读取方式：

- 第 1 段：`start_line=1, end_line=250`
- 第 2 段：`start_line=251, end_line=500`
- 第 N 段：严格从上一段最后请求行的下一行开始

禁止重叠、跳行、倒退或根据内容猜测下一起始行。

---

## 4. EOF 的唯一判定方式

对于每个运行时源文件：

1. 按固定行窗口持续读取；
2. 即使某一段已经出现完整 JSON 结束括号，也不得仅凭视觉判断结束；
3. 必须继续请求下一个连续窗口；
4. 只有下一个窗口返回“源文件无内容/空内容”时，才确认上一窗口已经到达真实源文件 EOF；
5. 确认 EOF 后，才允许拼接全部已读取源文件内容并做 JSON 解析与字段校验。

因此：

`JSON visually closed != confirmed EOF`

`next source window empty == confirmed EOF`

---

## 5. 避免 response-resource 分页

目标是从源头避免 Connector 对超大响应生成 response resource。

如果某个固定行窗口仍然因为返回过大而触发 `truncated`、response resource 或 continuation：

1. 不得把该 response resource 作为正常分页路径继续依赖；
2. 将同一源文件、同一起始位置的窗口缩小，例如 250 → 100 → 50 行；
3. 使用更小的 `fetch_file(start_line/end_line, ref=locked_sha)` 重读该段；
4. 直到该段能作为完整源文件行区间返回；
5. 然后继续后续连续窗口。

核心原则：

> 优先缩小“源文件读取窗口”，而不是追逐 response-resource continuation。

若 Connector 在 resource EOF 处重复相同 continuation，则不得因此陷入无限循环，也不得因此结束任务；应回到同一源文件、同一 SHA、明确源文件行区间继续推进。

---

## 6. 分片完成条件

单个候选 shard 只有同时满足以下条件才记为 completed：

1. 已确认真实源文件 EOF；
2. 全部连续行窗口无缺口、无重叠；
3. JSON 可完整解析；
4. `schema_version == 2`；
5. `trade_date` 与本轮 `meta` 一致；
6. `shard_index` 与文件序号一致；
7. `candidate_count == len(candidates)`。

不得因为“已经读到最后一个候选”“看到 `}`”“已得到足够候选”而提前标记完成。

---

## 7. 全局 Completion Gate

进入正式研究前必须同时满足：

- `completed_candidate_files == meta.shard_count`；
- 实际完成文件集合与 `meta.candidate_files` 完全一致；
- 所有 shard 代码无重复；
- `len(all_candidates) == meta.candidate_count == meta.snapshot.counts.candidates`；
- `industry_count == len(industries) == meta.industry_count`；
- 每只候选的 `industry_code` 均能映射到行业状态；
- 所有文件来自同一 `locked_sha`；
- 不存在未完成的源文件窗口读取。

只有完成上述 Gate 后，才允许开始行业复核、同行择优、公司确认、估值、低风险准入、赔率比较与正式排名。

---

## 8. `snapshot_read_incomplete` 的允许条件

只有以下情况才允许输出 `snapshot_read_incomplete`：

- 文件在锁定 SHA 下确实不存在；
- 固定源文件窗口读取经过缩窗重试仍无法取得所需源文件内容；
- 已确认源文件 EOF 后 JSON 仍不合法；
- 日期、schema、shard_index、candidate_count 等最终校验失败；
- 全局 Completion Gate 失败。

以下情况本身都不是失败理由：

- 单次工具响应显示 `truncated`；
- response resource 出现 continuation；
- response resource 在 EOF 处重复相同 continuation；
- 已经进行很多次工具调用；
- 上下文较长。

---

## 9. 终止前强制检查

输出任何最终结果前必须确认：

`pending_source_window == false`

`completed_candidate_files == meta.shard_count`

`global_runtime_validation == passed`

任一条件不满足时，禁止输出正式榜单，也禁止把“仍可继续读取”误报为读取失败。

# A股低风险买点榜：运行时读取协议

> 本文件只约束运行时数据读取、完整性校验和研究阶段边界。选股、行业判断、同行比较、公司研究、估值、买点与排名规则，以同一锁定提交下的 `skill/SKILL.md` 为准。

## 1. 唯一正式流程

本任务只保留一套正式流程，不再区分旧版、新版或兼容流程，也不允许回退到历史读取方式。

核心流程：

```text
机械候选全集
    ↓
完整读取所有公司的财务与行业比较摘要
    ↓
逐行业判断景气，形成行业覆盖记录
    ↓
按真实业务和核心盈利驱动分组，组内比较
    ↓
自然产生需要深读的公司
    ↓
完整公司研究与估值
    ↓
当前买点榜 / 等待池 / 淘汰及理由
```

核心原则：

> **全量轻读，行业全覆盖，真实业务分组，组内择优，自然产生深读名单。**

`deep_read_codes` 的数量是研究结果，不是输入约束。禁止设置任何全局最小值、最大值或目标数量，也不得为了控制工具调用、上下文长度或市场风险而提前删除本应研究的公司。

---

## 2. 新 run 与提交锁定

每一次新的定时触发、手动触发或用户明确要求重新执行，都视为全新 run：

1. 重新解析仓库 `xwan008/a-market-data` 当前 `main` commit SHA，记为 `locked_sha`；
2. 本轮所有仓库文件必须来自同一个 `locked_sha`；
3. 固定顺序读取：
   - `skill/RUNTIME_READ_PROTOCOL.md`
   - `skill/SKILL.md`
   - `data/runtime/meta.json`
4. 禁止复用上一轮的 SHA、读取进度、行业覆盖记录、公司分组、候选集合或 detail 读取结果。

如果只是继续同一 run 尚未完成的读取，则保持原 `locked_sha`，从当前阶段继续，不重复已经完整校验的源文件窗口。

---

## 3. 正式运行时入口

正式机械数据入口只有：

- `data/runtime/meta.json`
- `meta.industry_state_file`
- `meta.screening_file`
- `meta.detail_file_template` 指向的、本轮自然产生的深读公司 detail 文件
- `skill/SKILL.md`

不得读取旧 candidate shard、历史榜单、旧候选池或其他历史运行时文件来补齐正式候选。

`data/snapshot.json` 是数据生成源，不是正式研究运行时入口。

---

## 4. 数据新鲜度与生成期校验

读取 `meta.json` 后必须确认：

- `runtime_validation.status == "passed"`；
- `meta.snapshot.trade_date` 存在；
- `meta.snapshot.market_status` 与当前应使用的最近有效 A 股收盘一致；
- 非交易日允许沿用最近有效收盘；
- 如果当前正式收盘数据理应已经更新而 runtime 仍停留在更早交易日，则不得发布新的正式榜单。

生成期校验至少应证明：

- 候选代码唯一；
- `source_candidate_count` 与 snapshot 候选数一致；
- `screening_count == source_candidate_count`；
- `detail_count == screening_count`；
- 行业数量一致；
- 每个候选都能映射到行业；
- 每个候选都存在确定性的 detail 文件。

模型不需要为了重新证明这些不变量而读取全部 detail 文件。

---

## 5. 全量公司研究摘要

`screening_file` 必须完整覆盖机械候选全集。模型必须完整读取全部 rows 后，才允许进入行业覆盖与公司分组阶段；禁止边读边淘汰，也禁止因为已经发现“足够多候选”而提前停止。

轻量摘要至少应覆盖以下信息：

### 身份与行业
- `code`
- `name`
- `price`
- `industry_code`
- `industry_name`

### 财务与盈利质量
- `pe_ttm`
- `pe_dynamic`
- `pb`
- `market_cap`
- `roe`
- `revenue_yoy`
- `net_profit_yoy`
- `deduct_basic_eps_yoy`（可用时）
- `operating_cashflow_per_share`
- `gross_margin`
- `net_profit`

### 业务比较信息
如果运行时已有，则读取：
- `business_tags`
- `core_profit_driver`
- `major_business_segments`

如果这些字段缺失，不得凭公司简称或行业名称猜测真实盈利驱动。进入真实业务分组时，应仅对需要辨别的公司使用公司公告、定期报告、交易所资料等做最小必要补查。

### 价格结构
- `day_change_pct`
- `close_change_5d_pct`
- `close_change_20d_pct`
- `position_pct`
- `trend_state`
- `break_state`
- `ma20`
- `ma60`
- `support_center`
- `resistance_center`
- `invalidation_price`
- `invalidation_direction`

价格结构用于判断执行时机和风险边界，不得在轻量摘要阶段单独淘汰基本面质量较高的公司。

---

## 6. 行业文件与行业覆盖记录

`industry_state_file` 必须完整读取，并覆盖 runtime 中全部行业。

完成全量公司摘要读取后，必须逐行业形成覆盖记录，至少包含：

- 行业代码与名称；
- 当前景气基线；
- 盈利兑现强度与广度；
- 市场确认状态；
- 是否进入进一步研究；
- 若不进入，唯一主要原因。

不得只研究热点行业、资源品行业或当日强势行业。行业覆盖是正式研究的强制步骤。

---

## 7. 真实业务与核心盈利驱动分组

对景气复核通过或值得继续验证的行业，不能只按申万三级行业做同行比较，必须进一步按：

> **真实主营业务 + 核心盈利驱动 + 主要利润来源**

形成真实可比组。

规则：

- 同一三级行业内，如果利润驱动明显不同，必须拆组；
- 不同三级行业内，如果核心业务和盈利驱动高度一致，可以形成跨行业可比组；
- 对资源/强周期公司，还应考虑资源禀赋、成本曲线、自产比例、冶炼/加工占比、伴生品、产量弹性等；
- 对制造/科技公司，应考虑产品结构、客户结构、订单/出货、资本开支暴露、利润率驱动等；
- 不得仅凭行业标签把业务模式明显不同的公司机械地互相淘汰。

每个真实可比组原则上形成以下终态：

1. `winner`：组内最值得进入完整研究的公司；
2. `differential_candidate`：必要时额外保留具有明显不同风险收益、业务结构、资源禀赋、成本曲线或估值特征的公司；
3. `research_uncertain`：摘要证据不足或冲突，无法可靠判断时进入深读；
4. `excluded`：能够明确解释为何相对组内候选次优。

禁止为了满足某个全局数量目标而删除 `winner`、必要的 `differential_candidate` 或 `research_uncertain`。

---

## 8. deep_read_codes 的生成

只有以下步骤全部完成后，才允许确定 `deep_read_codes`：

1. 全量公司摘要读取完成；
2. 全部行业覆盖记录完成；
3. 所有继续研究的行业完成真实业务/盈利驱动分组；
4. 每个真实可比组完成组内比较并得到明确终态。

`deep_read_codes` = 所有组内 `winner` + 必要 `differential_candidate` + `research_uncertain` 的自然并集。

**不设全局数量上限，也不设全局数量下限。**

某轮可以自然产生 8、18、27、35 或更多深读公司，取决于当轮真实行业与公司结构。

市场风险高时不得缩减研究范围。市场风险只能提高后续：

- 估值安全边际；
- 买点质量；
- 风险收益比要求；
- 正式入榜门槛。

---

## 9. Detail 深读

只对 `deep_read_codes` 中的公司读取 `meta.detail_file_template` 对应 detail 文件。

每只 detail 必须：

- 来自同一 `locked_sha`；
- `trade_date` 与 meta 一致；
- `code` 与目标代码一致；
- `candidate` 为合法对象；
- 完整读取到真实 EOF。

未进入 `deep_read_codes` 的 detail 不要求读取，也不得因为没有读取全部 detail 而阻止任务继续。

---

## 10. 源文件窗口与真实 EOF

默认读取窗口：

- `meta.json`：最多 250 行；
- 单股 detail：最多 250 行；
- `industry_state_file`：默认 50 行连续窗口；
- `screening_file`：默认 50 行连续窗口。

如果窗口触发截断或返回过大：

1. 保持同一源文件和同一起始行；
2. 缩小窗口，例如 `50 → 25 → 10`；
3. 成功读取该段后再继续后续连续窗口。

禁止跳行、倒退、根据内容猜下一行或把 `truncated` 视为失败。

对需要完整读取的文件：

- 看到 JSON 结束括号不等于 EOF；
- 必须继续请求下一个连续源窗口；
- 只有下一个连续窗口为空，才确认真实 EOF。

只要仍存在可继续读取的必需源窗口，就必须继续，不得因上下文较长、工具调用较多或已经读取大量内容而主动停止。

---

## 11. Completion Gates

### Screening Completion Gate

必须同时满足：

- runtime 生成期校验通过；
- `industry_state_file` 已确认真实 EOF、可解析且数量一致；
- `screening_file` 已确认真实 EOF、可解析且覆盖全部机械候选；
- columns 与 `meta.industry_columns / meta.screening_columns` 一致；
- 每行长度与 columns 一致；
- 所有文件来自同一 `locked_sha`；
- `pending_source_window == false`。

### Research Allocation Gate

必须同时满足：

- 已完成全部行业覆盖记录；
- 所有继续研究的行业已完成真实业务/核心盈利驱动分组；
- 每个真实可比组都有明确的 `winner / differential_candidate / research_uncertain / excluded` 终态；
- 每个 `excluded` 至少存在一个可核验的主要理由；
- `deep_read_codes` 是上述结果的自然并集，没有全局数量截断。

### Deep Research Completion Gate

必须同时满足：

- Screening Completion Gate 通过；
- Research Allocation Gate 通过；
- `completed_detail_files == len(deep_read_codes)`；
- 实际完成 detail 的代码集合与 `deep_read_codes` 完全一致；
- 所有 detail 来自同一 `locked_sha`；
- `pending_source_window == false`。

只有全部通过后，才允许发布正式榜单。

---

## 12. 失败与继续读取边界

以下情况本身不是失败理由：

- 单次响应 `truncated`；
- response resource 出现 continuation；
- 工具调用次数较多；
- 上下文较长；
- 大量未被选中的 detail 没有读取；
- 深读公司数量超过过去习惯数量。

只有必需文件缺失、固定窗口缩小后仍无法取得内容、真实 EOF 后数据不可解析/校验失败、生成期校验失败，或上述 Completion Gate 无法满足时，才允许终止正式发布并明确报告失败点。

---

## 13. 审计要求

每轮正式结果至少保留以下阶段计数：

- `snapshot.trade_date`
- `mechanical_candidate_count`
- `industry_coverage_count`
- `eligible_industry_count`
- `comparison_group_count`
- `deep_read_codes_count`
- `company_confirmed_count`
- `low_risk_entry_admission_count`
- `asymmetry_passed_count`
- `final_recommendation_count`

同时必须生成 `notable_excluded_candidates` 审计：

对于明显的大市值龙头、行业代表、高盈利增长、较低估值、高 ROE 或高现金流质量公司，如果没有进入 deep-read，必须能够给出明确的行业层或组内比较理由。

如果无法给出充分理由，应加入 deep-read，而不是静默淘汰。

---

## 14. 最终边界

研究范围与买入门槛必须严格分离：

> **市场风险影响“买不买”，不能影响“值不值得研究”。**

因此：

- `bearish`、`transition`、60 日位置、靠近压力位、单日大跌等价格结构信息，可以降低执行优先级、影响等待条件和买点；
- 但这些因素不得单独成为全量摘要阶段淘汰高质量公司的理由；
- 最终淘汰应发生在行业、真实同行、公司质量、估值、安全边际、风险收益比或买点条件中，并留下可核验理由。

最终原则：

> **程序负责证明候选和数据完整；模型负责完成行业全覆盖、真实业务分组与组内择优；深读数量由研究自然产生；最终买点由估值、安全边际和风险收益决定。**

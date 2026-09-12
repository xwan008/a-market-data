# A股低风险买点榜：运行时读取协议

> 本文件只约束运行时数据读取、完整性校验和研究阶段边界。选股、行业判断、同行比较、公司研究、估值、买点与排名规则，以同一锁定提交下的 `skill/SKILL.md` 为准。

## 1. 核心原则

本任务采用：

> **生成侧保证数据完整，模型完整消费轻量 runtime，研究范围不得缩小。**

必须区分三件事：

- **数据完整性证明**：由 GitHub 数据生成流程完成；
- **全量轻量研究覆盖**：由模型基于已经通过校验的 compact runtime 完成；
- **公司真实业务研究**：只对自然进入 `deep_read_codes` 的公司执行。

**全量研究不等于模型重新逐行证明文件完整性，也不等于对全部机械候选逐家公司做公开资料检索。**

禁止为了再次证明行数、列数、唯一性或 EOF，而对已经通过生成期校验的 compact runtime 进行逐窗口手工扫描。

---

## 2. 新 run 与提交锁定

每次定时触发、手动触发或用户明确要求重新执行，都视为新 run：

1. 获取 `xwan008/a-market-data` 当前 `main` commit SHA，记为 `locked_sha`；
2. 本轮所有 GitHub 规则和 runtime 数据均来自同一 `locked_sha`；
3. 固定读取：
   - `skill/RUNTIME_READ_PROTOCOL.md`
   - `skill/SKILL.md`
   - `data/runtime/meta.json`
4. 禁止复用上一轮 SHA、候选集合、行业覆盖、公司分组或 detail 研究结论。

如果只是继续同一 run，则保持原 `locked_sha`，不得重新切换版本。

---

## 3. 正式 runtime 入口

只使用：

- `data/runtime/meta.json`
- `meta.industry_state_file`
- `meta.screening_file`
- `meta.detail_file_template` 指向的 deep-read 公司 detail
- `skill/SKILL.md`

不得读取旧 candidate shard、历史榜单或旧候选池补齐当前研究。

`screening_file` 是全量轻量研究输入，不要求预先包含公司的真实主营、核心盈利驱动或主要业务结构。此类公司级研究信息属于 deep research 阶段，不得因为 screening 中不存在 `business_tags`、`core_profit_driver`、`major_business_segments` 等字段而判定 runtime 失败。

---

## 4. 生成期完整性作为唯一机械校验来源

读取 `meta.json` 后，首先确认：

- `runtime_validation.status == "passed"`；
- `snapshot.trade_date` 与当前应使用的最近有效 A 股正式收盘一致；
- `screening_count == source_candidate_count`；
- `detail_count == screening_count`；
- `industry_count` 有效；
- meta 中声明的 integrity / validation 检查没有失败。

当上述生成期校验通过时，应直接信任生成侧已经验证的机械不变量，包括但不限于：

- 候选代码唯一；
- 行数与声明 count 一致；
- columns/schema 一致；
- 每个候选可映射到行业；
- 每个候选存在确定性的 detail；
- compact 文件内容完整。

**模型不得再次通过逐屏、逐窗口、额外空窗口或 EOF 探测来重新证明这些不变量。**

只有当 `runtime_validation` 失败、缺失，或 meta 自身出现 count/integrity 冲突时，才将其视为数据完整性问题并停止正式发布。

---

## 5. Compact runtime 的读取方式

`industry_state_file` 与 `screening_file` 是为模型研究准备的轻量 compact 数据。

模型必须消费其中的全部有效记录，用于实现：

- 全部行业覆盖；
- 全部机械候选进入行业/组内轻量研究流程；
- 不因已经发现足够多候选而提前停止。

但“消费全部有效记录”允许使用任何可靠方式：

- 一次性读取完整 payload；
- connector 返回的完整内容资源；
- 对锁定 SHA 下原始 compact 文件进行程序化加载/解析；
- 其他能够得到全部有效 records 的等价方式。

若某个工具界面发生展示截断，应优先切换到可完整消费 payload 的读取方式，**不得默认退回到 50 行、25 行、10 行逐窗口翻页，更不得为了确认所谓“真实 EOF”持续请求空窗口。**

工具展示是否截断，不等于 runtime 数据不完整。

---

## 6. 全行业与全候选覆盖

研究范围必须完整：

- 覆盖 `industry_count` 对应的全部行业；
- 覆盖 `screening_count` 对应的全部机械候选；
- 不得只研究热点行业、资源品或当日强势方向；
- 不得边读取边因价格、趋势或个人偏好提前删除候选。

这里的“全候选覆盖”是指每个机械候选都必须进入基于 compact 数据的轻量研究与初始分组流程，**不要求对全部候选逐家公司搜索公开资料、确认真实主营或建立完整公司画像。**

行业与公司研究规则服从 `SKILL.md`。

模型不需要再次输出或机械重算全部行业、候选的 count 来证明自己读完；只需要保证研究逻辑确实基于完整 compact 数据执行。

---

## 7. 初始分组与 deep_read_codes

完成全行业覆盖和全候选轻量研究后：

1. 允许直接使用 runtime 已提供的申万三级行业作为**初始可比组**；
2. 在初始组内结合行业状态、基本面、估值、盈利变化、现金流、价格位置、支撑/成交密集区、趋势与失效结构进行轻量比较；
3. 前置轻量比较的目标不是完成最终同行结论，而是识别哪些公司值得进入公司级深度研究；
4. 对于业务异质性明显、数据冲突、估值可能存在周期失真、行业映射可能不足以解释公司盈利的候选，应保守进入 `research_uncertain`，而不是在前置阶段直接淘汰；
5. `deep_read_codes` 为所有轻量比较后仍具有潜在安全边际、潜在明显上行空间、代表性、差异化价值或研究不确定性的公司自然并集。

`deep_read_codes` 不设全局数量上限或下限。

不得因为市场风险、上下文长度、工具调用数量或历史习惯而缩小 deep-read 范围。

**形成 `deep_read_codes` 之前，不得强制要求所有候选拥有 `business_tags`、`core_profit_driver`、`major_business_segments`，也不得要求先对全部候选完成真实主营业务分组。**

---

## 8. Detail 深读与真实业务分组

只读取 `deep_read_codes` 对应的 detail 文件。

每只 detail 只需确认：

- 来自同一 `locked_sha`；
- `trade_date` 与 meta 一致；
- `code` 与目标代码一致；
- 内容可完整取得并足够支持正式研究。

**detail 同样不要求通过额外空窗口证明“真实 EOF”。**

如果 connector 已经返回完整对象或可程序化解析的完整文件，即视为完成读取。

未进入 `deep_read_codes` 的 detail 不要求读取。

对所有 `deep_read_codes`，在 deep research 阶段再通过 detail 与必要的公开资料确认：

- 真实主营业务 / `business_tags`；
- 核心盈利驱动 / `core_profit_driver`；
- 主要业务与利润来源 / `major_business_segments`；
- 当前行业机会是否真实传导到公司；
- 一次性收益、周期高点或其他可能扭曲表面估值的因素。

完成公司确认后，再按：

> **真实主营业务 + 核心盈利驱动 + 主要利润来源**

进行最终真实业务分组。申万三级行业只负责前置初始分组，不强制作为最终可比组。

如果 deep research 发现原初始行业组内公司实际不可比，应重新分组；如果发现跨三级行业公司具有相同核心盈利驱动，也允许在最终研究中形成真实可比组。

每个最终真实可比组必须形成明确终态：

- `winner`
- `differential_candidate`
- `research_uncertain`
- `excluded`

---

## 9. Completion Gates

### Runtime Gate

必须同时满足：

- `runtime_validation.status == passed`；
- trade date 正确；
- meta count / integrity 没有冲突；
- 规则与数据均来自同一 `locked_sha`。

不再包含：

- 人工逐窗口 EOF 验证；
- `pending_source_window`；
- 为重新证明唯一性、行数和 columns 而重复扫描原始文件；
- 对 screening 候选预先检查真实主营、盈利驱动或主要业务字段是否存在。

### Research Coverage Gate

必须同时满足：

- 全行业已进入覆盖流程；
- 全部机械候选已进入三级行业初始分组与轻量比较流程；
- 前置轻量研究没有因为缺少公司级业务字段而中断；
- 所有值得继续研究或存在合理不确定性的公司均自然进入 `deep_read_codes`；
- `deep_read_codes` 没有全局截断。

**Research Coverage Gate 不要求在 deep-read 之前完成真实主营业务分组。**

### Deep Research Gate

必须同时满足：

- Runtime Gate 通过；
- Research Coverage Gate 通过；
- 所有 `deep_read_codes` 对应 detail 已完成研究；
- 所有 detail 来自同一 `locked_sha`；
- 所有 `deep_read_codes` 已完成真实主营、核心盈利驱动和主要利润来源确认；
- 必要的真实业务重新分组已经完成；
- 每个最终真实可比组存在明确终态。

只有以上 Gate 通过后才能发布正式榜单。

---

## 10. 失败边界

以下情况**不是失败，也不得导致任务卡住**：

- 工具 UI 对大文件展示 `truncated`；
- 单次 connector 输出没有把全部内容展示在聊天窗口；
- compact 文件包含数百个行业或候选；
- 没有执行额外 EOF 空窗口请求；
- 未读取非 deep-read 公司的 detail；
- screening 中不存在公司级 `business_tags`、`core_profit_driver`、`major_business_segments`；
- 前置阶段只使用申万三级行业进行初始分组。

真正失败只包括：

- `runtime_validation` 未通过；
- 当前应有的正式 runtime 缺失或过期；
- 锁定 SHA 下必需文件无法取得；
- compact 数据无法以任何可靠方式完整消费；
- Research Coverage Gate 或 Deep Research Gate 无法完成。

若一种读取方式受限，应切换读取方式继续研究，而不是把“工具展示截断”误判成“数据读取失败”。

---

## 11. 收盘版与早间增量版

### 收盘正式版

基于当前锁定 SHA 的 validated compact runtime 完成全行业、全候选轻量研究，以三级行业作为初始分组形成自然的 `deep_read_codes`，再对 `deep_read_codes` 完成公司级真实业务研究、最终分组、估值与买点判断。

### 早间隔夜增量版

仍重新读取当前规则与 meta，但允许以上一有效收盘版的**决策结论**作为比较基准，只复核隔夜新增信息是否改变：

- 行业景气；
- 公司盈利；
- 安全边际；
- 向上空间；
- 重大风险与失效条件。

不得把早间增量版重新退化成完整逐行数据校验。

---

## 12. 终止前版本复核

正式结果发布前重新检查 `main` 当前 SHA：

- 若仍等于 `locked_sha`，正常发布；
- 若 main 已变化，本轮仍以原 `locked_sha` 的数据与规则完成并明确标记版本变化；
- 不得在同一 run 中途混用新旧 SHA。

---

## 13. 最终原则

> **GitHub 负责证明 runtime 完整；模型负责研究完整。**

> **全量覆盖 ≠ 全量公司公开资料检索。**

> **三级行业负责前置初分组；真实主营与盈利驱动负责 deep research 阶段的最终分组。**

> **validated compact runtime 一旦通过生成期校验，就直接用于研究，不重复做机械验数。**

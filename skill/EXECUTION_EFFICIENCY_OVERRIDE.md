# A股低风险买点榜｜执行效率 Override

本文件只覆盖 `RUNTIME_READ_PROTOCOL.md`、`SKILL.md` 以及现有各 Override 中与执行顺序、外部 I/O、重复研究、批处理、缓存和证据预算有关的规则。它不降低 Transmission、Expectation、Risk–Reward、价格区间完整性或发布 Gate 的研究标准。

## 1. 目标

将日常正式版从“逐家公司串行深研”改为：

```text
一次性读取运行数据
→ 按三级行业完成轻量预筛
→ 每行业 Top 5 / 并列第6
→ 按行业批量做 Transmission
→ 仅对 SUPPORTED 做 Expectation
→ 仅对需要闭合的公司做 Risk–Reward / 价格区间
→ 优先复用同交易日未失效缓存
```

研究完整不等于无限搜索。任务必须在明确证据预算内完成分类；证据不足时使用 `UNCERTAIN`，不得为了追求结论而无限追加外部查询。

## 2. 一次性读取原则

1. 同一轮执行中，`trend_handoff.json`、`theme_alias_map.json`、`runtime/meta.json`、`company_industry_index.json`、正式协议与 Override 文件原则上只读取一次。
2. 需要读取个股 shard 时，先确定本轮全部 routed / hard-eligible / pre-screen selected 公司，再按 shard 前缀去重；同一 shard 不得为不同公司重复读取。
3. 已经读取到本轮上下文中的公司价格、财务、估值和60日结构，不得为了同一字段重复访问仓库或 Web。
4. 禁止为了逐家公司方便而重复 fetch 超大索引文件。

## 3. 分阶段缩容

执行顺序必须严格为：

```text
Routing
→ Hard Filter
→ Pre-screen
→ Transmission
→ Expectation
→ Risk–Reward / Price Range
```

每层只处理上一层仍需继续研究的公司：

- `PRE_SCREENED_OUT`：停止，不做 Web 深研；
- Transmission=`NOT_SUPPORTED`：直接进入 DROP，停止 Expectation / Risk–Reward；
- Transmission=`UNCERTAIN`：进入 UNCERTAIN，除非已有明确缺口可在一次补证内闭合，否则停止；
- 只有 Transmission=`SUPPORTED` 才进入 Expectation；
- 只有 EARLY / CONFIRMING / 新预期重置，或需要闭合 WAIT_EXPECTATION 的公司进入完整 Risk–Reward 与价格区间计算。

不得对已在上游明确终止的公司继续做后续研究。

## 4. 按行业批处理

1. Web / 公告 / IR 研究的基本批次是“三级行业”，不是“单家公司”。
2. 同一三级行业入选的 1–6 家公司，应尽量在同一批研究请求中覆盖，例如一次核验该行业全部候选的订单、交付、产能、客户、价格/价差、在手订单和核心利润变化。
3. 批处理结果必须回填到各家公司独立结论，不得因为批量研究而模糊公司差异。
4. 只有某家公司存在独有重大缺口时，才允许额外单独补证。

## 5. 同交易日研究缓存

允许复用同交易日已完成的正式或手动研究结果，但必须满足全部条件：

```text
trade_date 相同
company_code 相同
runtime trade_date / runtime blob 未变化
trend_handoff 对该公司的来源趋势未发生实质变化
公司没有新增重大公告/事件足以改变结论
```

缓存可复用：
- 已核验的一手证据摘要；
- Transmission 结论；
- Expectation 时间链中未变化的事实；
- 正常化盈利假设和价格区间基础参数。

不得机械复用：
- 已因新公告、业绩预告、监管事件、重大订单、重大股价变化而失效的结论；
- 价格已明显越过原区间或触发失效条件后的 Risk–Reward 结论。

正式结果中可记录 `cache_reused_codes` 与 `cache_invalidated_codes` 作为审计字段。

## 6. 有限证据预算

### 6.1 Transmission

每家公司原则上最多需要：
- 1 个核心一手证据来源；
- 必要时 1 个交叉验证来源。

若在该预算内仍无法证明未来1–2季度盈利传导，则记 `UNCERTAIN`，不得无限搜索。

### 6.2 Expectation

优先使用：
- runtime 价格结构；
- 已确认催化日期；
- 最近财报/公告；
- 已验证的订单/产能/交付信息。

除非事件时间线冲突，不得为同一公司重复发起多轮相似搜索。

### 6.3 Risk–Reward / Price Range

优先使用仓库已有：
- 当前价格；
- PE/PB 等估值；
- 收入/利润/扣非/现金流；
- 60日支撑区、阻力区、成交密集区、position_pct。

Web 只用于补正常化盈利和关键前瞻假设，不得把价格区间计算变成第二轮全面深研。

## 7. 外部调用纪律

1. 能批量查询的，不得拆成逐家公司串行查询。
2. 能从当前已读文件得到的，不得再上 Web。
3. 同一 URL / 同一公告 / 同一文件在一轮中不得重复读取，除非前次结果不完整。
4. 若某一外部查询失败，不得无限重试；一次合理替代源仍失败则记录证据缺口并按 UNCERTAIN 处理。
5. 不得为了“看起来更完整”增加与最终状态无关的背景资料。

## 8. 执行审计

正式结果新增可选审计字段：

```json
"execution_audit": {
  "routed_company_count": 0,
  "deep_research_company_count": 0,
  "industry_batch_count": 0,
  "cache_reused_count": 0,
  "cache_invalidated_count": 0,
  "single_company_followup_count": 0
}
```

这些字段用于判断是否退化回逐家公司串行执行。

若出现以下任一情况，应视为执行路径异常并在结果备注中说明：
- `single_company_followup_count` 接近或超过 `deep_research_company_count`；
- 同一大文件被重复读取多次；
- PRE_SCREENED_OUT / NOT_SUPPORTED 公司仍继续做后续深研；
- 同交易日基础数据未变化却从零重做全部公司研究。

## 9. 不允许的优化

以下行为禁止以“提速”为理由执行：
- 降低每行业 Top 5/6 的预筛完整性；
- 跳过已入选公司的 Transmission coverage；
- 为了省查询直接假设订单/产能/客户传导成立；
- 省略价格区间完整性；
- 把证据不足的公司强行归类 READY/WAIT；
- 因已找到 READY 而提前停止其他已入选公司的完整 coverage。

## 10. 目标执行形态

正常情况下，当前 2–3 个趋势信号、约 3–5 个三级行业的正式版应表现为：

```text
少量仓库批量读取
+ 约等于三级行业数量的批量行业研究
+ 少量真正必要的单公司补证
```

而不是：

```text
深研公司数 × 多轮独立搜索
```

如无法在有限证据预算内完成，则应扩大 UNCERTAIN，而不是扩大查询次数。

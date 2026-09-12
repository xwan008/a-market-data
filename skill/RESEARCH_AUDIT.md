# 研究记录保存与校验

本契约用于收盘完整研究及新正式榜发布，补充 Skill 的同行比较和审计要求。记录是研究过程中产生的证据索引，不是重新复制整份行情或深读全部公司。

## 文件与版本

```text
data/research_runs/<run_id>/
  run.json                 本轮清单、锁定数据提交、重点关注代码
  industries.json          全部 runtime 行业的去向记录
  groups/<group_id>.json    每个真实可比组一份，含成员比较与最终去向
```

`run_id` 使用日期、时段和唯一后缀；同一交易日重新执行必须另起目录。不要放进 `data/runtime`（数据重建会替换它）。同一 run 可以逐组保存进度；新 run 不能把旧记录改名后声称重新研究完成。

`locked_sha` 始终指向本轮读取的规则与数据提交。保存记录产生的 `audit_commit` 是另一个提交，只用于定位证据。校验从 `locked_sha` 取 runtime，不能切换到写入后的 main。

## 生成初始记录

有 Python 和当前仓库文件时，在锁定提交的工作副本执行：

```bash
python scripts/research_audit.py init \
  --runtime-dir data/runtime \
  --output data/research_runs/20260912-close-001 \
  --run-id 20260912-close-001 \
  --locked-sha <本轮完整40位提交SHA>
```

可用 `--notable 601899 002475 000338 605020` 记录本轮用户关注的例子；代码必须来自候选池。它们没有入榜特权。按 Skill 的代表公司标准补充本轮值得解释的其他公司。

生成器只填写身份信息，全部行业状态为 `pending`、阶段为 `collecting`，不会伪造研究。没有 Python 的执行环境，可以通过已授权的 GitHub 文件工具按下面格式逐文件保存；不要求下载所有单股 detail 来生成模板。

`run.json`：

```json
{
  "run_id": "20260912-close-001",
  "locked_sha": "填写本轮完整40位SHA",
  "trade_date": "2026-09-11",
  "stage": "collecting",
  "group_files": [],
  "notable_codes": []
}
```

`group_files` 列出实际存在的全部组文件，例如 `groups/copper-mining.json`。保留稳定的组 ID，防止保存中途丢组。不要并发覆盖同一个文件；使用工具要求的当前文件 blob SHA 进行更新。

## 行业记录

`industries.json` 是数组，每个 runtime 行业恰好一条：

```json
{
  "industry_code": "S240302",
  "decision": "research",
  "reason": "填写景气基线、领先变量和继续研究的原因",
  "source_refs": ["填写带日期的来源URL或锁定runtime路径及字段"]
}
```

终态为 `research / uncertain / excluded / no_candidates`。`pending` 只能暂存，不能通过分配检查。

- `excluded` 要有行业层面的证据和原因，不能仅因市场整体风险高或短期价格弱。
- `no_candidates` 只适用于该行业没有机械候选的情况，引用本轮候选清单即可；这属于覆盖记录，不宣称完成公司研究。
- `research / uncertain` 行业中的全部候选必须进入一个主要可比组，不能只记胜出者。

## 同行记录

每个 `groups/<group_id>.json` 保存 `group_id`、`business_basis`（真实业务可比的理由）、`source_refs`（分组证据）、`members` 数组。跨行业组可以存在；每个候选只归属一个主要审计组，多元业务差异在组内说明，防止重复计数。

每个 member 必须包含：

```json
{
  "code": "股票代码",
  "decision": "research_uncertain",
  "reason": "研究分配理由",
  "comparisons": {
    "earnings_quality": {"status": "assessed", "finding": "核心/扣非盈利、持续性及同组差异", "source_refs": ["来源及字段/页码"]},
    "cashflow": {"status": "assessed", "finding": "同报告期现金流及质量差异，或适用于该行业的替代证据", "source_refs": ["来源及字段/页码"]},
    "valuation": {"status": "uncertain", "finding": "缺少何种估值证据、为什么需要补读", "source_refs": ["已查来源及缺口位置"]}
  }
}
```

`decision` 为 `winner / differential_candidate / research_uncertain / excluded`。任何未确定的比较都允许保留深读，不能填空、猜数字后标记 assessed。相对估值比较不要求提前算最终目标价，但必须讨论价格是否补偿盈利质量差异。

组内 `excluded` 额外必填：

- `preferred_codes`：同组仍被保留的竞争对手代码数组；
- `revisit_condition`：什么变化会使该公司重新胜出；
- 三项 comparisons 全部 assessed，有判断及来源。只因为利润规模落后而未比较估值，校验失败。

资料已经查过但不足以支持判断时，写明缺口并保留 `research_uncertain`，不能编造调查结论以满足校验。

## 分配完成与深读去向

行业、分组和比较全部保存后，将 `run.stage` 设为 `allocation`。校验精确检查全部候选分别属于行业排除或组内决策，随后从保留者自然生成 `deep_read_codes`。此阶段的通过不允许正式发布。

逐组完成深读后，为每个保留成员增加：

```json
{
  "detail_read": {"locked_sha": "本轮完整40位SHA", "path": "data/runtime/details/股票代码.json", "eof_confirmed": true},
  "outcome": {
    "status": "waiting",
    "stage": "entry",
    "reason": "本轮最终等待或淘汰主因；推荐时说明通过依据",
    "source_refs": ["支持本结论的实际来源及位置"],
    "company_confirmed": true,
    "entry_admitted": false,
    "asymmetry_passed": false
  }
}
```

`status` 是 `recommended / waiting / excluded`，`stage` 是 `company / valuation / entry / asymmetry / ranking`。推荐必须通过公司确认、低风险准入和非对称机会检查。阶段结果如实填写，程序据此生成计数。没有进入深读的公司已经由行业或组内排除记录解释，不需另写重复明细。

最终全部成员有去向后将 stage 设为 `final`，包括正式空榜。只保存“最终0只”而不解释此前研究去向，不能通过。

## 校验和实际保存

本地校验（runtime 必须是本轮锁定提交的文件）：

```bash
python scripts/research_audit.py validate data/research_runs/20260912-close-001 \
  --runtime-dir data/runtime --expected-sha <本轮完整40位SHA> \
  --report-dir audit-reports/20260912-close-001
```

退出码：0 = final 通过；2 = collecting 或 allocation，不可正式发布；1 = 校验失败。以 JSON 中的 stage/status/publishable 判断，不能把 allocation 的退出码2误判为研究失败。

GitHub 执行环境：通过仓库文件工具逐组保存记录，更新 run.json 清单。推送到 main 会触发 `Validate Research Audit` 工作流；同一次写入可批量提交多个已完成组，避免每条记录单独提交。也可以在可用时手动触发工作流，传入 `run_dir`。保存动作须在当前会话已授权范围内；未获写入能力时输出附件并说明“审计待保存验证”，不得声称后台已保存。

工作流只读取 runtime 和已保存的研究记录，不自动编写投资判断，不自动发布榜单。它从记录的 locked_sha 提取 runtime，验证结果以 Actions artifact 保存90天；原始行业和组记录保存在 Git 历史中。正式结果引用本次工作流、审计提交和报告的 `audit_sha256`，不能沿用旧绿色状态。

输出报告：

- `validation.json`：阶段计数、深读集合、重点公司去向、输入文件哈希；
- `company_outcomes.json`：全部候选按股票代码索引，指向原始组/行业记录，含最终去向。

工作流成功并不自动等于可以发布：collecting 会成功暂存但报告 incomplete；allocation 会通过结构检查但 publishable=false。只有本轮 final 的 status=passed 且 publishable=true 才满足审计门禁。任何修改后的记录都需要重新验证哈希。

校验器验证集合覆盖、引用、字段和状态的一致性，不能证明模型真的读过文件，也不能判断来源真实性或投资推理是否正确；这些仍需通过来源和记录人工核查。禁止把模板或测试数据作为真实审计提交。

## 隔夜增量

无变化的早间增量答复引用上一有效收盘的已验证审计，并说明本轮检查的变化，不宣称重新完成全量研究。若发布新的正式榜单，必须提供本轮可验证的完整去向记录；增量研究得到的变动与所引用的基准结论都要标明来源，不能复用旧校验哈希冒充新结果。本契约不要求无变化的早间答复重复全部公司深读。

# A股低风险买点榜｜执行效率规则

## 1. 目标

在不降低研究标准的前提下，将正式版稳定执行为：

```text
一次展开 routed industries
→ 逐行业读取 manifest + 全部有界 parts
→ 动态生成每行业 working set
→ Freeze
→ Hard Filter
→ Pre-screen Top5/6
→ 按行业批量 Transmission
→ SUPPORTED 才进入 Expectation；EARLY_EVIDENCE 独立观察
→ 必要对象进入估值与 Price Range
```

不得退化为逐家公司反复读取仓库或多轮串行 Web 搜索。

---

## 2. 仓库 I/O 规则

数据生产层（GitHub Actions）：

1. `company_industry_index.json` 作为 Universe 权威来源；
2. `data/shards/*.json` 作为公司事实权威来源；
3. `scripts/build_low_risk_working_sets.py` 每次有效收盘更新后全量执行 deterministic join/projection；
4. 输出 `data/low_risk/index.json`、每行业 `manifest.json + part-xxx.json`；迁移期同时保留 legacy 单行业文件但正式榜不得读取；
5. 每 part 默认最多 5 家且 <=96 KiB；
6. 只有 mapped company coverage、industry partition、trade_date、industry mapping、chunk coverage、chunk size 全部校验通过才允许提交。

正式榜运行时 Freeze 前：

1. `trend_handoff.json` 原则上读一次；
2. `data/low_risk/index.json` 原则上读一次；
3. 每个 routed 行业读取一次 manifest；
4. 按 manifest 声明完整读取全部 parts；每个有界多行 JSON part 默认一次完整文件读取到 EOF，只有工具明确返回截断、响应大小限制或无法获得完整 EOF 时，才以 100–150 行为一段连续分页，不抽样、不跳行；已完整返回的 part 禁止再次分页或重读，完整解析成功后才算一个逻辑 part read；
5. 将 parts 拼接并校验覆盖后形成 run-local working set；
6. 全部 routed 行业工作集完成后统一 Freeze。

Freeze Gate：

```text
working_set_company_count == universe_company_count
working_set_count == routed_industry_count
materialized_manifest_read_count == routed_industry_with_universe_count
materialized_part_read_count == routed manifests 声明的 part_count 总和
materialized_part_segment_fetch_count >= materialized_part_read_count
materialized_industry_complete_count == routed_industry_with_universe_count
legacy_industry_file_read_count == 0
```

Freeze 后：

- `post_freeze_shard_read_count == 0`
- `post_freeze_materialized_read_count == 0`
- 不得读取 company_industry_index；
- 不得读取任何个股 shard；
- 不得再次读取 manifest / part；
- 不得读取 legacy materialized industry file；
- 不得读取 screening_groups_by_industry 作为低风险任务数据源；
- 所有内部公司事实只来自 frozen working set。

## 3. 分阶段缩容

Freeze 后严格：

```text
Hard Filter
→ Pre-screen
→ Transmission
→ Expectation
→ Risk–Reward / Price Range
```

- PRE_SCREENED_OUT：停止；
- Transmission=NOT_SUPPORTED：DROP，停止；
- Transmission=EARLY_EVIDENCE：进入独立观察池，记录公司直接关联证据、商业化缺口与下一次验证触发条件；停止，不进入 Expectation / READY / WAIT / handoff；
- Transmission=UNCERTAIN：只允许一次明确补证，否则停止；
- 只有 SUPPORTED 才进入 Expectation；EARLY_EVIDENCE 仅观察，不计入 READY / WAIT / handoff；
- 只有后续规则要求闭合的公司进入完整 Risk–Reward / Price Range。

---

## 4. Transmission 两步搜证（行业批量 + 按需补证）

**业务线检索覆盖要求（反漏查）**：行业批次建立“公司 → 当前趋势相关的具体产品/材料/工艺/设备/子公司业务线 → 商业化阶段”清单，使用产品同义词和披露用语（如送样、认证、小批量出货、订单、销售、交付/验收），而不是只搜公司的传统主营或趋势总名称；同组可批量并行，保持原有 2–3 家/组和一次定向补证预算。仅当材料、设备等的实际用途可归因到本轮主题时，才计作该趋势的商业证据。

**退出前证据一致性检查**：拟判 UNCERTAIN/NOT_SUPPORTED 的公司，逐一回答：（a）是否核实了直接产品/业务关联？（b）是否搜索了该业务线的商业化阶段，而不是只搜订单/利润？（c）有无可定位的一手出货、交付、客户认证、商业化项目线索与当前拟判状态冲突？存在可核查且可能改变状态的线索时必须按第 2 步定向补证并记录来源；必要补证未完成，不得以“无订单数据”认定 NOT_SUPPORTED 或宣布研究 COMPLETE。实际销售/设备交付可构成 SUPPORTED 的商业证据，但仍需独立通过后续价格及风险审核；只有研发/送样/中试而未证实商业化时使用 EARLY_EVIDENCE。

1. **一次行业批量搜证，内部按业务分组**：先为每家入选公司明确待核实的具体产品/业务及其与当期趋势的关联；同一行业按产业环节把业务相近的公司每 2–3 家组成一组，用短查询围绕产品、订单、交付、客户、产能、价格等关键事实并行检索。行业批量研究可以包含多条并行短查询，但不退化为逐家公司串行全面调查；不得把全行业多家公司和大量关键词塞入单条长查询。优先核验公司公告、正式财报、交易所披露和投资者关系记录，检索入口不限定单一网站。共享来源可复用，但必须逐家公司确认业务敞口。
2. **按需一次定向补证，先做遗漏检查**：批量检索后逐家检查：是否已有可归属该公司及当前趋势业务的近期证据；是否仅取得过期资料；是否只查到非关键业务、遗漏了可能影响结论的另一条相关业务。若公司存在具体、可核查的趋势业务关联，且上述缺口的补查可能改变 Transmission 判断，则须围绕该缺口执行最多一次个股定向补证。没有可核查的业务关联，或缺口即使补查也不会改变判断时，不机械逐家补查，但必须记录不补查的具体理由。无来源不能自动等同于“无需补查”。
3. **逐家公司给出判断并留痕**：记录本轮业务关联、所属批量分组/实际短查询、关键证据及来源（共享来源允许）、证据新鲜度、缺口、是否触发定向补证及执行结果或不补查理由，以及行业驱动→公司业务→商业传导证据/未来兑现窗口和 SUPPORTED / EARLY_EVIDENCE / NOT_SUPPORTED / UNCERTAIN。有效订单、客户认证或交付必须核实与本轮趋势直接相关；不能仅因缺少精确季度利润预测就判 UNCERTAIN。拟判 UNCERTAIN / NOT_SUPPORTED 时，必须核查已取得的一手资料中是否存在相矛盾的相关订单、客户认证或交付证据；存在具体可核查矛盾时，应在定向补证预算内优先处理，无法完成必要核查则记 RESEARCH_INCOMPLETE。没有取得来源时记录实际查询结果，不编造证据。

两步搜证已正常执行且完成必要证据冲突检查后仍有关键证据缺口，保留 UNCERTAIN；明确反证才给 NOT_SUPPORTED。已核实公司直接业务关联但仅处政策/技术/研发阶段、尚无可靠商业验证时记 EARLY_EVIDENCE。若搜证工具故障导致必要检索实际未完成，标记 RESEARCH_INCOMPLETE 并阻断发布，不把检索故障冒充公司基本面不确定。

---

## 5. 正式版 Fresh Run

19:00 正式版与手动正式版不得复用上一轮执行结果来跳过本轮步骤。每次都必须重新完成：Trend Handoff 路由、manifest/parts 完整读取、working set 构造与 Freeze、Hard Filter、Pre-screen、Transmission、Expectation、Risk–Reward / Price Range。

上一轮正式结果、上一轮研究摘要及上一轮公司状态只能在本轮完整计算结束后用于差异对比，不得作为本轮阶段结论输入。

07:00 早间增量版不受此条限制，按 `RUNTIME_READ_PROTOCOL.md` 复用上一份 COMPLETE。

---

## 6. 有限证据预算

### Transmission
执行第 4 节“两步搜证”：每行业一次研究批次，批次内按产业环节分组、每组 2–3 家公司并行短查询；只对存在可改变结论的关键缺口者最多一次定向补证。不强制每家公司单独取得公告或做第二轮检索，但无来源、过期来源、遗漏相关业务或拟判 UNCERTAIN / NOT_SUPPORTED 与已取得一手资料冲突时，必须先评估并执行必要补证。正常检索后：已核实直接业务关联但尚无可靠商业验证 → EARLY_EVIDENCE；关键事实仍无法闭合 → UNCERTAIN；必要检索未完成 → RESEARCH_INCOMPLETE。

### Expectation
优先：
- frozen working set 的价格结构；
- 已确认催化日期；
- 最近财报/公告；
- 已验证订单/产能/交付信息。

### Risk–Reward / Price Range
优先使用 frozen working set：
- 当前价格；
- PE/PB/ROE；
- 收入/利润/扣非/现金流；
- MA20/MA60；
- 60日高低；
- support/resistance；
- dense/volume-profile zones；
- position_pct。

Web 只补关键前瞻假设，不得变成第二轮全面估值深研。

---

## 7. 外部调用纪律

1. 能批量不串行；正式榜运行时按 routed industry 读取 manifest + 有界 parts，不再现场读取/解析 shards；
2. working set 已有字段不再上 Web；
3. 同一 URL/公告同轮不重复读；
4. 查询失败最多使用一次合理替代源；
5. 不增加与最终状态无关的背景资料。

---

## 8. 执行审计

正式结果推荐：

```json
{
  "data_access_audit": {
    "routed_industry_count": 0,
    "universe_company_count": 0,
    "working_set_count": 0,
    "working_set_company_count": 0,
    "materialized_index_read_count": 1,
    "materialized_manifest_read_count": 0,
    "materialized_part_read_count": 0,
    "materialized_part_segment_fetch_count": 0,
    "materialized_industry_complete_count": 0,
    "legacy_industry_file_read_count": 0,
    "unique_shard_read_count": 0,
    "post_freeze_shard_read_count": 0,
    "post_freeze_materialized_read_count": 0
  },
  "execution_audit": {
    "deep_research_company_count": 0,
    "industry_batch_count": 0,
    "single_company_followup_count": 0
  }
}
```

异常条件包括：

- working_set_company_count != universe_company_count；
- post_freeze_shard_read_count > 0；
- 正式榜运行时直接读取了 company_industry_index 或 shard；
- 同一 manifest 或 part 被再次读取；
- legacy industry file 被正式榜读取；
- single_company_followup_count 接近 deep_research_company_count；
- PRE_SCREENED_OUT / NOT_SUPPORTED 仍继续后续深研；
- EARLY_EVIDENCE 被错误送入 Expectation、READY / WAIT 或 handoff；
- 入选公司缺少逐家公司业务关联、所属批量短查询、证据缺口及补证决定的可追溯记录；存在可改变结论的缺口却未执行必要补证或未说明不补证理由；必要检索发生工具故障却被当作 UNCERTAIN；
- 正式版或手动正式版复用上一轮阶段结论、从而跳过本轮任一阶段。

---

## 9. 不允许的优化

不得以提速为理由：
- 降低 Top5/6 预筛完整性；
- 跳过入选公司的 Transmission；
- 假设订单/产能/客户传导成立，或未核验订单与本轮趋势的直接关联；
- 省略价格区间；
- 把证据不足强行归 READY/WAIT；
- 因已有 READY 提前停止其他入选公司。

正常形态应是：

```text
约等于 routed 行业数量的 manifests + manifest 声明的全部 parts
+ 约等于 routed 行业数量的 working sets
+ 约等于 routed 行业数量的批量行业研究
+ 少量真正必要的单公司补证
```

## 10. 独立影子估值计算的资源边界

前瞻影子研究不是正式版新增硬 Gate，不应延迟或阻断19:00正式发布、07:00增量或业务JSON持久化。只在正式研究完全完成之后，针对已发布的 SUPPORTED 和已有 EARLY_EVIDENCE 中的代表性案例使用已有一手证据或明确追加的独立情景来源；不得为凑齐三情景而逐只无限搜证，也不得修改第2–9节I/O/两步搜证预算。证据不足只写 `INSUFFICIENT_EVIDENCE`；禁止因 shadow 异常失败正式发布。规则详见 `FORWARD_VALUATION_SHADOW_PROTOCOL.md`。

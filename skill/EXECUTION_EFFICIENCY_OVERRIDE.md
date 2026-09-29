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
→ SUPPORTED 才进入 Expectation
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
- Transmission=UNCERTAIN：只允许一次明确补证，否则停止；
- 只有 SUPPORTED 才进入 Expectation；
- 只有后续规则要求闭合的公司进入完整 Risk–Reward / Price Range。

---

## 4. Transmission 两步搜证（行业批量 + 按需补证）

1. **一次行业批量搜证，内部按业务分组**：先为每家入选公司明确待核实的具体产品/业务及其与当期趋势的关联；同一行业按产业环节把业务相近的公司每 2–3 家组成一组，用短查询围绕产品、订单、交付、客户、产能、价格等关键事实并行检索。行业批量研究可以包含多条并行短查询，但不退化为逐家公司串行全面调查；不得把全行业多家公司和大量关键词塞入单条长查询。优先核验公司公告、正式财报、交易所披露和投资者关系记录，检索入口不限定单一网站。共享来源可复用，但必须逐家公司确认业务敞口。
2. **按需一次定向补证，先做遗漏检查**：批量检索后逐家检查：是否已有可归属该公司及当前趋势业务的近期证据；是否仅取得过期资料；是否只查到非关键业务、遗漏了可能影响结论的另一条相关业务。若公司存在具体、可核查的趋势业务关联，且上述缺口的补查可能改变 Transmission 判断，则须围绕该缺口执行最多一次个股定向补证。没有可核查的业务关联，或缺口即使补查也不会改变判断时，不机械逐家补查，但必须记录不补查的具体理由。无来源不能自动等同于“无需补查”。
3. **逐家公司给出判断并留痕**：记录本轮业务关联、所属批量分组/实际短查询、关键证据及来源（共享来源允许）、证据新鲜度、缺口、是否触发定向补证及执行结果或不补查理由，以及行业驱动→公司业务→未来 1–2 季度盈利机制和 SUPPORTED / NOT_SUPPORTED / UNCERTAIN。没有取得来源时记录实际查询结果，不编造证据。

两步搜证已正常执行后仍有关键证据缺口，保留 UNCERTAIN；明确反证才给 NOT_SUPPORTED。若搜证工具故障导致必要检索实际未完成，标记 RESEARCH_INCOMPLETE 并阻断发布，不把检索故障冒充公司基本面不确定。

---

## 5. 正式版 Fresh Run

19:00 正式版与手动正式版不得复用上一轮执行结果来跳过本轮步骤。每次都必须重新完成：Trend Handoff 路由、manifest/parts 完整读取、working set 构造与 Freeze、Hard Filter、Pre-screen、Transmission、Expectation、Risk–Reward / Price Range。

上一轮正式结果、上一轮研究摘要及上一轮公司状态只能在本轮完整计算结束后用于差异对比，不得作为本轮阶段结论输入。

07:00 早间增量版不受此条限制，按 `RUNTIME_READ_PROTOCOL.md` 复用上一份 COMPLETE。

---

## 6. 有限证据预算

### Transmission
执行第 4 节“两步搜证”：每行业一次研究批次，批次内按产业环节分组、每组 2–3 家公司并行短查询；只对存在可改变结论的关键缺口者最多一次定向补证。不强制每家公司单独取得公告或做第二轮检索，但无来源、过期来源或遗漏相关业务时必须先评估补证必要性并留痕。正常检索后仍无法闭合 → UNCERTAIN；必要检索未完成 → RESEARCH_INCOMPLETE。

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
- 入选公司缺少逐家公司业务关联、所属批量短查询、证据缺口及补证决定的可追溯记录；存在可改变结论的缺口却未执行必要补证或未说明不补证理由；必要检索发生工具故障却被当作 UNCERTAIN；
- 正式版或手动正式版复用上一轮阶段结论、从而跳过本轮任一阶段。

---

## 9. 不允许的优化

不得以提速为理由：
- 降低 Top5/6 预筛完整性；
- 跳过入选公司的 Transmission；
- 假设订单/产能/客户传导成立；
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

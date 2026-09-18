# A股低风险买点榜｜执行效率规则

## 1. 目标

在不降低研究标准的前提下，将正式版稳定执行为：

```text
一次展开 Universe
→ 去重 shard 后小批次读取并工具内投影目标公司事实
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
4. 输出 `data/low_risk/index.json` 与 `data/low_risk/by_industry/*.json`；
5. 只有 mapped company coverage、industry partition、trade_date、industry mapping 全部校验通过才允许提交。

正式榜运行时 Freeze 前：

1. `trend_handoff.json` 原则上读一次；
2. `data/low_risk/index.json` 原则上读一次；
3. 只读取 routed 三级行业对应的小文件，每个行业最多一次；
4. 每个行业文件直接形成一个 run-local working set，不再现场拼 shards；
5. 全部 routed 行业工作集完成后统一 Freeze。

Freeze Gate：

```text
working_set_company_count == universe_company_count
working_set_count == routed_industry_count
materialized_industry_read_count == routed_industry_count
```

Freeze 后：

- `post_freeze_shard_read_count == 0`
- `post_freeze_materialized_read_count == 0`
- 不得读取 company_industry_index；
- 不得读取任何个股 shard；
- 不得再次读取 materialized industry file；
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

## 4. Web / 公告 / IR 批处理

基本研究批次是三级行业，不是单家公司。

同一行业入选的 1–6 家公司应尽量在同一批研究中覆盖：

- 订单
- 交付
- 产能
- 客户
- 价格/价差
- 在手订单
- 核心利润变化

批量研究必须回填到各家公司独立结论。

只有某家公司存在独有重大证据缺口时，允许单独补证。

---

## 5. 正式版 Fresh Run

19:00 正式版与手动正式版不得复用上一轮执行结果来跳过本轮步骤。每次都必须重新完成：Universe 展开、shard 收集、working set 构造与 Freeze、Hard Filter、Pre-screen、Transmission、Expectation、Risk–Reward / Price Range。

上一轮正式结果、上一轮研究摘要及上一轮公司状态只能在本轮完整计算结束后用于差异对比，不得作为本轮阶段结论输入。

07:00 早间增量版不受此条限制，按 `RUNTIME_READ_PROTOCOL.md` 复用上一份 COMPLETE。

---

## 6. 有限证据预算

### Transmission
每家公司原则上：
- 1 个核心一手来源；
- 必要时最多再 1 个交叉验证来源。

无法在预算内闭合 → UNCERTAIN。

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

1. 能批量不串行；正式榜运行时按 routed industry 直接读取预物化小文件，不再现场读取/解析 shards；
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
    "materialized_industry_read_count": 0,
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
- 同一 materialized industry file 被再次读取；
- single_company_followup_count 接近 deep_research_company_count；
- PRE_SCREENED_OUT / NOT_SUPPORTED 仍继续后续深研；
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
约等于 routed 行业数量的 working sets
+ 约等于 routed 行业数量的批量行业研究
+ 少量真正必要的单公司补证
```

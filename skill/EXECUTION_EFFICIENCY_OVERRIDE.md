# A股低风险买点榜｜执行效率规则

## 1. 目标

在不降低研究标准的前提下，将正式版稳定执行为：

```text
一次展开 Universe
→ 去重 shard 一次性读取
→ 动态生成每行业 working set
→ Freeze
→ Hard Filter
→ Pre-screen Top5/6
→ 按行业批量 Transmission
→ SUPPORTED 才进入 Expectation
→ 必要对象进入估值与 Price Range
→ 复用未失效的同交易日研究结论
```

不得退化为逐家公司反复读取仓库或多轮串行 Web 搜索。

---

## 2. 仓库 I/O 规则

Freeze 前：

1. `trend_handoff.json` 原则上读一次；
2. `company_industry_index.json` 原则上读一次；
3. 先得到完整 `universe_company_codes`；
4. 由全部 universe codes 计算所需 shard 前缀；
5. shard 前缀去重后，每个 shard 最多读取一次；
6. 从这些 shard 一次性提取本轮公司完整事实；
7. 动态构造每个 routed 三级行业的 run-local working set。

Freeze Gate：

```text
working_set_company_count == universe_company_count
working_set_count == routed_industry_count
```

Freeze 后：

- `post_freeze_shard_read_count == 0`
- 不得再读取 company_industry_index；
- 不得再逐股读取 shard；
- 不得读取 screening_groups_by_industry 作为低风险任务数据源；
- 所有内部公司事实只来自 frozen working set。

---

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

## 5. 同交易日研究缓存

这里的“缓存”只指**研究结论缓存**，不指公司事实数据缓存。

允许复用同交易日已经完成的：
- 一手证据摘要；
- Transmission 结论；
- 未变化的 Expectation 时间链；
- 关键前瞻假设。

必须满足：

```text
trade_date 相同
company_code 相同
runtime 基础事实未变化
trend_handoff 来源趋势未实质变化
无新增重大公告/事件使结论失效
```

公司事实本轮仍以 frozen working set 为唯一内部来源。

不得把 `screening_groups_by_industry`、compact cache 等重新引入正式主链。

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

1. 能批量不串行；
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
    "unique_shard_read_count": 0,
    "post_freeze_shard_read_count": 0
  },
  "execution_audit": {
    "deep_research_company_count": 0,
    "industry_batch_count": 0,
    "research_cache_reused_count": 0,
    "research_cache_invalidated_count": 0,
    "single_company_followup_count": 0
  }
}
```

异常条件包括：

- working_set_company_count != universe_company_count；
- post_freeze_shard_read_count > 0；
- 同一 shard 重复读取；
- single_company_followup_count 接近 deep_research_company_count；
- PRE_SCREENED_OUT / NOT_SUPPORTED 仍继续后续深研；
- 同交易日无变化却从零重做全部公司研究。

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

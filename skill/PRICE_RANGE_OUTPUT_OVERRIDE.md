# A股低风险买点榜｜价格区间与榜单输出 Override

本文件只覆盖 `RUNTIME_READ_PROTOCOL.md` / `SKILL.md` / `PRE_SCREEN_RESEARCH_SCOPE_OVERRIDE.md` 中关于正式榜单价格区间完整性、最终状态归类和用户可见输出的冲突规则。其他路由、预筛、Transmission、Expectation、Risk–Reward 规则保持不变。

## 1. 核心目标

正式“A股低风险买点榜”必须是可直接使用的价格榜单，而不是只给状态标签。

凡进入正式 `READY` 或 `WAIT` 榜单的公司，必须同时给出：

- `current_price`
- `reasonable_price_range`
- `low_risk_buy_range`
- `wait_reason`（READY 可为空）
- `price_range_basis`
- `reentry_trigger`

其中 `reasonable_price_range` 与 `low_risk_buy_range` 禁止写 `N/A`、`待估值`、`待确认`、空字符串或 null。

## 2. 价格区间定义

### 合理买入区

`reasonable_price_range`：在未来 1–2 个季度正常化盈利假设下，使用保守估值并预留基本不确定性后，仍具备可接受风险收益比的价格区间。

### 低风险买入区

`low_risk_buy_range`：在合理买入区基础上进一步加入更严格安全边际、下行锚和事件风险折价后的价格区间。正常情况下应低于或不高于合理买入区。

价格区间必须优先综合：

1. 未来 1–2 季度前瞻/正常化盈利；
2. 保守估值倍数或可辩护的历史/同业估值区间；
3. 当前 60 日价格结构、主要支撑/成交密集区；
4. 主要风险事件的折价要求；
5. 至少 15% 左右保守上行空间作为低风险候选的重要参考，而非机械硬公式。

不得仅按技术支撑位生成“合理价值区”，也不得只按历史 PE 分位机械外推。

## 3. 无法可靠估值时的状态

若进入 Risk–Reward 后仍无法可靠给出 `reasonable_price_range` 或 `low_risk_buy_range`，则该公司：

- 不得保留在 `READY`；
- 不得保留在 `WAIT_PRICE / WAIT_MARGIN / WAIT_CATALYST / WAIT_EXPECTATION`；
- 必须转入 `UNCERTAIN`；
- `uncertain_stage` 记为 `RISK_REWARD` 或更准确的冲突阶段；
- `reason` 必须明确说明为什么正常化盈利、保守估值或安全边际无法建立。

因此，正式榜单中不允许存在“状态是 WAIT，但买入区间是 N/A”的记录。

## 4. WAIT 的含义

只有已经完成价格区间计算、但当前价格或催化条件尚未满足时，才允许使用 WAIT：

- `WAIT_PRICE`：价格仍高于合理/低风险区；
- `WAIT_MARGIN`：已有可辩护价格区间，但当前安全边际不足；
- `WAIT_CATALYST`：已有可辩护价格区间，但仍需订单、利润、产能或客户验证等催化确认；
- `WAIT_EXPECTATION`：已有可辩护价格区间，但当前预期已较充分计价，需要新的预期重置或价格回到对应区间。

WAIT 必须同时保存明确的 `reentry_trigger`。

## 5. Coverage

正式版新增：

```text
price_range_coverage = COMPLETE
```

满足条件：

```text
all READY + WAIT
都具有：
current_price
reasonable_price_range
low_risk_buy_range
price_range_basis
reentry_trigger
```

只有同时满足：

```text
materialized_view_gate = PASSED
trend_handoff_gate = PASSED
routing_coverage = COMPLETE
pre_screen_coverage = COMPLETE
transmission_coverage = COMPLETE
expectation_coverage = COMPLETE
risk_reward_coverage = COMPLETE
price_range_coverage = COMPLETE
publication_ready = true
```

才允许覆盖 `research/latest_formal_result.json`。

## 6. 用户可见榜单

每次 19:00 正式版或手动正式执行，最终必须优先输出主榜单，至少包含：

| 公司 | 方向 | 当前价 | 合理买入价位 | 低风险买入价位 | 状态 | 等待/触发条件 |
|---|---|---:|---:|---:|---|---|

展示顺序：

1. READY；
2. WAIT；
3. 如无 READY，明确写“本轮无 READY”，但仍完整展示 WAIT 榜单；
4. UNCERTAIN / DROP / PRE_SCREENED_OUT 只做简短附表或数量摘要，不得喧宾夺主。

主榜单不得省略价格区间。正式结果即使内部 COMPLETE，但若用户可见输出没有主榜单，也视为输出不完整。

## 7. 研究纪律

- 不为了填数字而伪造估值区间；
- 无法形成可辩护估值时宁可转 UNCERTAIN；
- 榜单价格区间是研究结果，不是保证成交或收益；
- 当前价必须来自本轮正式收盘 frozen working set；
- 价格区间若因新财报、订单、重大事件或价格大幅波动失效，应在下一次正式版重新计算。
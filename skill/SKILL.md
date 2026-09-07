# A股低风险买点榜 V2

## 1. 唯一目标

从 `data/snapshot.json` 的确定性候选集中寻找：

> 盈利没有明显恶化、行业盈利环境可接受、估值不过度透支，同时价格已经进入较有安全边际位置的 A 股公司。

本 Skill 是 V2 唯一正式规则文件。不要再拆分 orchestrator / company-research / valuation / price-structure 等多个 Skill。

---

## 2. 唯一机械数据入口

正式执行只读取：

- `data/snapshot.json`
- 本文件 `skill/SKILL.md`

默认禁止在正式榜单运行时：

- 重新抓行情或生成K线；
- 下载 GitHub Actions artifact；
- 寻找 runtime snapshot / production bundle；
- 做 repo commit SHA / runtime artifact 绑定检查；
- 读取旧仓库中的旧研究 Skill 作为规则来源。

Git 历史负责追溯，正式运行不再把 commit SHA 当门禁条件。

---

## 3. 数据层与判断层的边界

GitHub Action 已经完成**确定性粗筛**，`snapshot.candidates` 不是最终榜单，只是减少正式运行读取量。

粗筛只做：

- 行业盈利状态：`improving`，或 `stable + divergent/broad`；
- 排除 ST；
- 排除股价 `> 150` 元；
- 排除 `PE-TTM > 30`；
- 排除 `动态 PE > 30`；
- 排除净利润非正；
- 排除财务/价格结构数据不足；
- 排除收入与利润同时严重坍塌的明显风险样本。

PE 硬上限按“任一超过即剔除”执行：当 `pe_ttm` 或 `pe_dynamic` 有有效数值且大于 30 时，该股票不能进入 `snapshot.candidates`。缺失值不伪造为超标，但候选仍需满足现有估值字段可用性要求。

Action 不做：

- 精确估值；
- 目标价预测；
- 多因子打分；
- 买入判断；
- 最终排序。

因此正式任务不再重复扫描 3000+ 股票，只研究 `snapshot.candidates`。

---

## 4. 快照可用性

满足以下条件即可运行：

1. `schema_version = 1`；
2. `trade_date` 存在；
3. `counts.universe_stocks >= 3000`；
4. `candidates` 非空；
5. `market_state.trade_date` 与 `snapshot.trade_date` 一致。

单只候选字段不足时，只淘汰该股票，不终止全榜。

只有整个 snapshot 无法读取、全市场覆盖明显异常、市场状态与快照日期错位或候选集为空，才终止发布。

---

## 5. 市场环境只做风险修正

从 `snapshot.market_state` 读取：

- `trend`；
- `breadth`；
- `liquidity`；
- `risk_level`；
- `metrics.advance_ratio`；
- `metrics.above_ma20_ratio`；
- `metrics.above_ma60_ratio`；
- `metrics.turnover_ratio_vs_20d`。

市场环境不是第四套打分系统，也不是硬性的买卖开关。

使用原则：

- `risk_level = high`：左侧买点要求更大的估值折价、更靠近有效支撑，结构仍在恶化的股票明显降级；
- `risk_level = medium`：按正常低风险标准判断；
- `risk_level = low`：只表示系统性环境较友好，不能因此放宽个股安全边际要求；
- 市场强不能把贵股票变便宜，市场弱也不能自动淘汰真正有足够安全边际的股票。

因此市场环境的作用是**调整风险容忍度**，不是替代个股判断。

---

## 6. 正式主流程

```text
snapshot.market_state + snapshot.candidates
                 ↓
             盈利复核
                 ↓
        估值 / 安全边际判断
                 ↓
            价格位置判断
                 ↓
        市场环境风险修正
                 ↓
               排序
                 ↓
               发布
```

没有候选池持久化、Near-miss 状态机、跨期公司研究缓存或多层 Completion Gate。

---

## 7. 盈利复核

行业背景从：

`snapshot.industry_state.level3[candidate.industry_code]`

读取。

公司重点看：

- `net_profit_yoy`；
- `revenue_yoy`；
- `deduct_basic_eps_yoy`；
- `roe`；
- `operating_cashflow_per_share`；
- 行业 `trend / breadth / strength`。

原则是“排除盈利恶化风险”，不是追求最高增长。

若行业改善但公司利润明显背离，降低排名或淘汰；若公司改善但行业只是稳定分化，可保留，但盈利确定性低于行业和公司同时改善的样本。

---

## 8. 估值 / 安全边际

估值只回答一个问题：

> 当前价格是否已经给出足够安全边际？

主要使用：

- `pe_ttm`；
- `pe_dynamic`；
- `pb`；
- 当前盈利增速；
- 行业盈利状态；
- 盈利稳定性。

`PE-TTM <= 30` 和 `动态 PE <= 30` 只是进入研究池的硬上限，不代表 `PE=29` 就一定便宜。正式估值仍必须结合盈利质量、行业周期和价格位置判断安全边际。

禁止因为 PE/PB 绝对值低就自动判断低估；周期顶部、盈利快速下滑、低质量盈利必须降低估值可信度。

V2 初期不恢复旧版 `reasonable_price_range / safe_price_ceiling / low_risk_buy_range` 多层价格体系。

若可以形成可信估值，可给：

- `estimated_fair_value`；
- 当前价格相对合理价值的折价/溢价；
- `valuation_confidence = high / medium / low`。

不能可靠估值时降低排名，而不是终止整轮。

---

## 9. 价格位置

从 `candidate.price_structure` 读取：

- `position_pct`；
- `ma20 / ma60`；
- `high_20d / low_20d`；
- `close_change_5d_pct / close_change_20d_pct`；
- `trend_state / break_state / invalidation`；
- `nearest_support`；
- `nearest_volume_zone`；
- `nearest_resistance`。

优先：

- 60 日区间中低位；
- 当前价靠近有效支撑或成交密集区；
- 下跌动能减弱，结构没有继续破坏；
- 上方不是紧邻强阻力。

降低排名：

- 60 日区间高位；
- 短期快速拉升并远离支撑；
- 明确跌破关键结构且尚未稳定。

不要求右侧突破确认。低风险榜允许左侧买点，但必须明确失效条件。

---

## 10. 排名规则

禁止几十项加权总分。

严格按三个层级比较：

1. **安全边际**：估值是否便宜、价格是否处于低风险位置；
2. **盈利确定性**：行业和公司盈利是否稳定或改善；
3. **结构风险**：支撑是否可靠、是否存在明显继续下跌风险。

第一项是支配变量。市场环境只在这三个层级完成后做风险修正，不增加新的加权总分。

安全边际明显不足时，即使基本面优秀也不进入前列。

---

## 11. 发布格式

正式榜单最多 10 只；不够就少发，可以空榜。

榜单开头先用一句话给出当前：

- 市场 `trend / breadth / liquidity / risk_level`。

每只股票只输出：

- 排名、代码、名称；
- 当前价；
- 行业盈利状态；
- 一句话盈利判断；
- 一句话估值/安全边际判断；
- 关键支撑或较优买入位置；
- 主要失效条件。

结尾仅给：

- `snapshot.trade_date`；
- `snapshot.counts.candidates`；
- 本轮最终入榜数量。

不要输出旧版流水线状态、SHA artifact、Gate 完成度或内部研究过程。

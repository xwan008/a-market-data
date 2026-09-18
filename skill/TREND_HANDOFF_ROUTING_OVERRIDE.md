# A股低风险买点榜｜Trend Handoff Routing

## 1. 职责边界

本文件只负责：

```text
trend_handoff
→ resolved 三级行业
→ company_industry_index
→ 本轮 universe company codes
```

到此结束。

本文件不读取个股 shard、不做硬过滤、不做预筛、不做 Transmission / Expectation / Risk–Reward。

完整数据读取与 run-local working set 构造由 `LOW_RISK_CANONICAL_FLOW.md` 统一负责。

---

## 2. Routing 规则

1. 优先使用 `research/trend_handoff.json` 中已经明确的申万三级行业代码。
2. 已 resolved 的三级行业直接进入公司展开。
3. 不得使用 `industry_state` 的 trend / strength / breadth / confidence / buyability 作为买点榜准入或否决条件。
4. 不得使用 `screening_group_index.json`、`screening_groups_by_industry`、candidate cache 决定行业是否存在公司。
5. 唯一 Universe 来源：
   `data/research/company_industry_index.json`
6. 对每个 routed 三级行业按 `sw_level3_code` 展开当前策略主板 universe 的全部公司。
7. 同一公司被多个 trend signal / industry route 命中时，只保留一份公司事实，但保留全部趋势来源上下文。

---

## 3. Unresolved / Empty 语义

- handoff 行业映射成功，但 company_industry_index 中没有策略公司：
  `NO_UNIVERSE_MEMBER`
- 行业有公司但后续全部被公司级硬过滤：
  `NO_ELIGIBLE_COMPANY`
- 只有 handoff 与显式人工 alias 都无法确定三级行业代码时：
  `ROUTING_UNRESOLVED`

禁止使用 `NO_RUNTIME_CANDIDATE`。

---

## 4. 输出给 canonical flow

Routing 只输出：

- routed industry codes / names
- universe_company_codes
- 每家公司对应的 trend_name / trend_state / market_state 来源上下文

随后交给 canonical flow：

```text
Universe
→ 去重 shard 一次性读取
→ run-local working set
→ Freeze
```

三级行业代码只承担身份与路由功能，不重复判断行业景气。

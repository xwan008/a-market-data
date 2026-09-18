# A股低风险买点榜｜Trend Handoff Routing

## 1. 职责边界

本文件只负责：

```text
trend_handoff
→ resolved 三级行业
→ data/low_risk/index.json
→ routed industry materialized file
→ 本轮 universe company codes
```

到此结束。

本文件不读取原始 company_industry_index / 个股 shard，不做硬过滤、不做预筛、不做 Transmission / Expectation / Risk–Reward。

完整数据读取与 run-local working set 构造由 `LOW_RISK_CANONICAL_FLOW.md` 统一负责。

---

## 2. Routing 规则

1. 优先使用 `research/trend_handoff.json` 中已经明确的申万三级行业代码。
2. 已 resolved 的三级行业直接进入公司展开。
3. 不得使用 `industry_state` 或任何 Legacy Runtime 的 candidate/screening 结果作为买点榜准入、否决或排序条件。
4. 数据生产层的 Universe 权威仍是 `data/research/company_industry_index.json`；正式榜运行时不直接读取它。
5. 正式榜运行时以已校验的 `data/low_risk/index.json` 作为行业存在性与 company_count 索引，并读取对应 `data/low_risk/by_industry/<industry_code>.json` 得到完整 `universe_company_codes`。
6. 若 `data/low_risk/index.json` 已通过全量覆盖校验，而 routed 行业代码不在 `industries` 中，则语义为 `NO_UNIVERSE_MEMBER`；只有 index 无效、trade_date 不匹配，或 index 已列出行业但对应文件缺失/无效时才属于数据链缺口。不得回退旧 runtime 或现场解析大 JSON。
7. 同一公司被多个 trend signal / industry route 命中时，只保留一份公司事实，但保留全部趋势来源上下文。

---

## 3. Unresolved / Empty 语义

- handoff 行业映射成功，且 materialized index 明确 company_count == 0：
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
Materialized Industry View
→ run-local working set
→ Freeze
```

三级行业代码只承担身份与路由功能，不重复判断行业景气。

# Trend Handoff Routing Override

本文件只覆盖 A股低风险买点榜的 Trend Handoff / Routing 入口规则；与 `RUNTIME_READ_PROTOCOL.md` 或 `SKILL.md` 冲突时，本文件优先。

## 核心规则

1. 只要 `research/trend_handoff.json` 中的 signal 已经得到明确申万三级行业代码，就直接进入公司展开。
2. 不得再使用该三级行业在 `industry_state` 中的 `trend / strength / breadth / confidence / buyability` 作为准入或否决条件。
3. 不得因为该行业不在 `screening_group_index.json` 中，就判定为 `NO_RUNTIME_CANDIDATE`。
4. 使用 `data/research/company_industry_index.json`，按 `sw_level3_code` 展开该三级行业在当前策略主板 universe 中的全部公司。
5. 再读取这些公司的 `data/shards/<股票代码前5位>.json`，取得当日价格、财务与趋势结构数据。
6. 只允许公司级硬过滤：ST、无效/非正价格、净利润非正、关键估值/财务/趋势数据缺失、营收同比 < -20% 且净利润同比 < -50% 等既定公司级条件。不得加入任何行业景气条件。
7. 公司级硬过滤后得到 routed company universe，再完整执行 Transmission → Expectation → Risk–Reward。
8. 行业映射成功但策略主板 universe 中没有任何公司时，记录 `NO_UNIVERSE_MEMBER`；存在公司但全部被公司级硬过滤剔除时，记录 `NO_ELIGIBLE_COMPANY`。
9. `ROUTING_UNRESOLVED` 只用于 handoff 与 `theme_alias_map` 都无法确定三级行业代码的情况。
10. 三级行业代码只承担身份与路由功能；行业景气判断已经由趋势榜完成，不得在买点榜重复否决。

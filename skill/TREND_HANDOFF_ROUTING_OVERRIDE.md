# A股趋势买点榜｜Trend Handoff Routing

## 1. 职责边界

本文件只负责：

```text
trend_handoff
→ resolved 三级行业
→ data/low_risk/index.json
→ routed industry manifest
→ manifest parts
→ 本轮 universe company codes
```

到此结束。

本文件只校验和传递行业身份；公司过滤、预筛、业务证据和交易买点均由后续研究流程承担。

完整数据读取与 run-local working set 构造由 `TREND_BUY_CANONICAL.md` 统一负责。

---

## 2. Routing 规则

1. 使用 `research/trend_handoff.json` 中已经核验的申万三级行业代码进行行业路由。
2. 行业身份、名称及市场状态直接沿用本轮handoff，不在公司榜中重复计算板块状态。
3. 数据生产层的Universe以 `data/research/company_industry_index.json` 生成；研究阶段以完成日期及覆盖校验的 `data/low_risk/index.json`、各行业manifest与声明的全部parts为公司事实权威。
4. Manifest的 `universe_company_codes` 必须与所有parts的公司身份、顺序、总数严格一致，完成一次读取后冻结研究工作集。
5. Routed行业不在通过完整性校验的index中时标记 `NO_UNIVERSE_MEMBER`；已有映射但日期/manifest/parts校验失败时标记明确数据错误并停止该行业研究。
6. 多条趋势信号命中同一公司时，保留唯一公司事实及每个趋势的来源上下文。

---

## 3. Unresolved / Empty 语义

- handoff 行业映射成功，且 materialized index 明确 company_count == 0：
  `NO_UNIVERSE_MEMBER`
- 行业有公司但后续全部被公司级硬过滤：
  `NO_ELIGIBLE_COMPANY`
- 只有 handoff 与显式人工 alias 都无法确定三级行业代码时：
  `ROUTING_UNRESOLVED`


---

## 4. 输出给 canonical flow

Routing 只输出：

- routed industry codes / names
- universe_company_codes
- 每家公司对应的 trend_name / trend_state / market_state 来源上下文

随后交给 canonical flow：

```text
Manifest + all declared parts
→ run-local working set
→ Freeze
```

三级行业代码只承担身份与路由功能，不重复判断行业景气。

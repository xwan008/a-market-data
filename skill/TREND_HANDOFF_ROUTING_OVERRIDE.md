# A股趋势买点榜｜Trend Handoff Routing

## 1. 职责边界

本文件只负责：

```text
已正式发布并通过身份先行验证的 trend_handoff
├─ INDUSTRY: 申万三级行业 Codes → data/low_risk/index.json → manifest/parts
└─ THEME: 概念Code + 同日已核实主板Top20快照 → 每只的真实申万行业Code → manifest/parts
→ 本轮冻结的实际研究股票集合
```

到此结束。

本文件只校验和传递已正式确认的板块身份；公司过滤、预筛、业务证据和交易买点均由后续研究流程承担。主题类型不得在19:00临时重算涨跌幅后决定。

完整数据读取与 run-local working set 构造由 `TREND_BUY_CANONICAL.md` 统一负责。

---

## 2. Routing 规则

1. 先验证 `research/trend_handoff.json` 的 `source.identity_verified_before_state=true`、已冻结身份快照、对应当日主题Top20快照（行业型也保留日期路由文件），并要求股票池、原研究T/市场状态与handoff完全一致；未接通新身份流程时不得将旧格式快照冒充正式验证结果。
2. **INDUSTRY**：只使用已核验的 `industry_codes` 执行原申万三级行业路由；不在此处重复生成行业成员候选列表。
3. **THEME**：必须先核验概念Code和当日完整主板成员，再执行**直接产业链商业证据硬门槛**：每只进入Top20的公司，须有对应本轮产业驱动的直接供货/设备/系统集成/商业化控制软件业务，附确切发行人报告的细分业务已确认收入或正式签订可执行客户订单，以及定量金额、披露时间、报告定位、产业链环节和重要性评估；调用 `scripts/validate_theme_business_chain.py` 核验独立证据快照，概念标签、研发、参股、MOU、泛自动化客户及交易所主页均不算。**先筛商业实质，后对合格主板公司按既有机会分最多选20只**；不足20只不得凑数、缺证据不得进入正式买点研究。所属申万行业Code仅用于读取公司事实，不扩充主题股票池。
4. 板块身份、名称及模型评估后的产业T阶段/市场状态直接沿用本轮handoff；买点榜不得再升级或降级趋势状态。
5. 数据生产层的Universe以 `data/research/company_industry_index.json` 生成；研究阶段以完成日期及覆盖校验的 `data/low_risk/index.json`、各行业manifest与声明的全部parts为公司事实权威。
6. Manifest的 `universe_company_codes` 必须与所有parts的公司身份、顺序、总数严格一致，完成一次读取后冻结研究工作集。
7. Routed行业不在通过完整性校验的index中时标记 `NO_UNIVERSE_MEMBER`；已有映射但日期/manifest/parts校验失败时标记明确数据错误并停止该行业研究。
8. 多条趋势信号命中同一公司时，保留唯一公司事实及每个趋势的来源上下文。

---

## 3. Unresolved / Empty 语义

- handoff 行业映射成功，且 materialized index 明确 company_count == 0：
  `NO_UNIVERSE_MEMBER`
- 行业有公司但后续全部被公司级硬过滤：
  `NO_ELIGIBLE_COMPANY`
- 身份来源冲突：`MAPPING_UNRESOLVED`；真实概念成员/行情缺失：`DATA_INSUFFICIENT`。两者在正式买点任务中必须中止该方向研究，不得回退成行业路由。
- 只有旧版数据缺少可信行业身份时：`ROUTING_UNRESOLVED`，也不能作为新规则已核验的INDUSTRY。


---

## 4. 输出给 canonical flow

Routing 只输出：

- INDUSTRY: routed industry codes / names（由原manifest展开）
- THEME: verified concept code + dated Top20 mainboard candidate codes（由所属行业manifest核实公司事实）
- 本轮实际冻结研究公司代码
- 每家公司对应的 trend_name / trend_state / market_state 来源上下文

随后交给 canonical flow：

```text
Manifest + all declared parts
→ run-local working set
→ Freeze
```

申万/概念代码只承担身份与路由功能，不重复判断行业或产业趋势；公司研究、评分与READY/WAIT风险门槛不变。

### THEME商业证据审计口径（不能“炒概念”）

- 输入独立文件 `--business-evidence-file`，带 `as_of_trade_date`、真实概念Code、原产业驱动、独立复核责任标识、每只公司与对应产业环节、`RECOGNIZED_SEGMENT_REVENUE` 或 `SIGNED_EXECUTABLE_CUSTOMER_ORDER` 及实际金额、报告期间与披露日期、**精确到某份发行人披露文件与页码/章节**的URL与引用。
- 允许伺服电机、减速器、传感器、控制器、工业机器人本体/系统集成、直接商业软件等有证据的环节；用户/使用方、蹭热点合作、概念概述、笼统“公司总营收增长”不代表机器人业务收入。
- 为防止任意规模业务被当成产业驱动，须留存每只公司的`materiality_assessment`和业务相关营收/订单在当期趋势中的传导解释；不能验证收入和订单的**金额归属与重要性**时不入选。暂不自行创造统一“收入占比必须5%”等阈值，不改变原风险/趋势阈值。
- 无证据时输出显式阻断 `THEME_BUSINESS_PROOF_REQUIRED_BEFORE_TOP20` 或 `THEME_NO_VERIFIED_COMMERCIAL_CHAIN_TOP20_CANDIDATES`，不得以技术高分、次日概念成分或旧Top5补齐。
- 代码验证证据结构和准入字段；**原始披露内容是否真实支持该金额与机器人业务归属仍要求独立人工核查**。不得把填满JSON字段当作事实成立。


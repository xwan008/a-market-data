# A股趋势买点榜｜V2唯一研究、执行和发布契约

**状态：CANDIDATE_SHADOW，尚未晋升正式调度。** 本协议拟替换“低风险PE买点榜”的买点阶段；**不改变**已有上游“A股板块趋势榜”、原行业映射、原冻结公司池、Top5/并列第6预筛、公司基本面风险过滤、商业关联事实审查、全量Coverage/Fresh Run证据审计和交易日校验。旧版正式result/handoff保留历史，只读，不原地重释旧price range。生效切换必须一次性升级 result/handoff→快照→盘中解释→定时任务，并校验通过；前置影子验证不自动晋升。

## 1. 唯一目标和边界

趋势买点榜仅回答：在已验证市场/产业趋势与公司级关联的前提下，是否**出现可执行的趋势入场结构**？在哪个价格区内执行？超过什么价格取消追入？什么条件说明结构错误，如何风险退出？

链路：
```
当日Trend Handoff（不篡改上游）
→ Manifest/Part冻结工作集 + Stage A硬过滤 + Stage B行业Top5/6
→ Stage C公司主题业务关联与风险过滤
→ Stage D个股同日价格结构确认（突破 / 回调，价格量能证据）
→ Stage E入场区间、失效价、最大可接受风险与退出条件
→ READY / WAIT / UNCERTAIN / DROP → 版本化handoff → 盘中执行（只监测不重选股）
```

**公司过滤≠买点确认。** PE/PB/盈利、经营现金流/MA60/结构健康度可影响筛选、风险标记，但**禁止**把PE估值锚、MA60、历史60日低点或折价后的所谓“合理价值”直接作为入场价格。短期过热不能单纯因创新高判负，必须结合成交、距MA20距离及入场损失衡量。市场轮动/Expectation仅为趋势是否持续的研究解释，不能凭新闻热度单独触发买入。

## 2. 上游兼容与数据门槛

- 日期全部 Asia/Shanghai；07:00用前一已完成正式交易日，19:00用当日正式收盘；遇非交易日自动跳过；不推断交易日。
- 原 `skill/LOW_RISK_CANONICAL_FLOW.md` **仅第2至5节的行业路由、manifest/index/part/Freeze、硬过滤和预筛流程**以及 `skill/PRE_SCREEN_RESEARCH_SCOPE_OVERRIDE.md` 预筛规则沿用。第6-9节中基于静态估值决定WAIT/READY、fundamental anchor、安全边际的部分**在V2不可继续适用**。其他历史研究协议只作为旧版本，不被V2调用决定买点。
- Frozen Working Set 的数据事实只从本轮已核验的行业物化工作集建立。禁止 Freeze 后重复读取 index、manifest、part、shard补价；上游价格缺失/旧数据不能后验补造。
- **独立结构输入**：构建市场每日已完成日K数据 `data/research/full_market_price_structure.json`（由 `scripts/build_full_market_price_structure.py` 从完成交易日行情和180日历史生成）。其 `reference_trade_date` 必须严格等于本轮 `trade_date`，候选记录 `data_status=verified`、`data_date=trade_date`、`history_points>=120` 才能做入场结论。结构数据为另一个**同日已建成、已发布且一致性验证通过的聚合视图**；如果正式 Freeze 已完成而该视图未准备好，停止该轮发布，不能回头读取shard补建或拿旧指标凑数。
- 结构视图必须源于同一根日度行情并验证当前价/收盘日期/公司身份与Frozen Working Set一致；差异超合理报价精度则 `STRUCTURE_PRICE_MISMATCH`，该公司UNCERTAIN并在审计披露。不凭空外推成交量。
- 不够120个有效日K时必须 UNCERTAIN；从预筛成功不能推导出买点准备就绪。
- 新版预筛 `0.45 growth + 0.25 quality +0.20 valuation_match +0.10 trend_health` 保留。PE/PB仅用于同业质量/估值风险过滤，**不把指标直接变成买价**。单行业Top5，差距<=0.03可含第6，覆盖率100%。

## 3. 公司证据与Transmission

- SUPPORTED：已核实行业主题直接商业订单、客户认证、正式项目/交付或经营传导。
- EARLY_EVIDENCE：真实技术/样品/研发业务关联，但商业化不足；**可继续观察趋势结构**，不是公司盈利已兑现的证据。只有 `theme_link_verified=true`、已逐项完成重大经营现金流/稀释/概念归因风险审查 `early_evidence_risk_review_passed=true`，且交易结构也通过时才允许有条件 READY，且必须明确更高不确定性；不因股价上涨自动升级 SUPPORTED。保守阶段可保持WAIT_CONFIRMATION。
- UNCERTAIN：缺公司业务关联/关键财务资料/量价证据，不能给READY；NOT_SUPPORTED或硬过滤失败为DROP。
- 任何公司的重大退市风险、ST、不明股本变化、明显失真信息等必须先阻断。不存在“必须三情景预测未来EPS才能形成趋势买点”的条件；但同样不能以无法估值暗示便宜。

## 4. 唯一的两种入场结构

**突破 BREAKOUT**
1. 只用已完成收盘的当日K线与此前60/120日高位（计算压力位必须排除当日数据）；
2. 当前完成K线收于关键前高附近/上方，且成交比（当日对20日>=1.15，或5日对20日>=1.05）与收盘在当日振幅位置>=55%确认；
3. 价格位于上升结构，距MA20不过度延伸、追高风险不高；
4. 给出下一交易日允许的 `entry_zone`、绝对 `max_entry_price`、失败结构位及成本损失率；
5. 跳空超过上限取消，不能把“昨日收盘确认”冒充次日可在昨日价格成交。

**回调 PULLBACK**
1. 必须有有效上升趋势背景、MA60支撑和 `higher_low`；
2. 当日最低价触及MA20的合理容差范围，收盘重新站上MA20且高于前收盘，收盘位置>=55%；
3. 跌到均线本身不是买入信号；不能用过期Pivot/未观察的回踩路径冒充已出现的承接；
4. 同样给出入场价格上限、结构失效与跳空风险。

**风险收益**：V2初版试验参数（**非经回测证明最优**）为结构入场损失上限6%、距MA20>8%或chase=high禁追、已知第一上方阻力若不足1.5R则WAIT。没有可信阻力不伪造涨幅目标，采用趋势保护退出。风险预算只以认错成本控制仓位，实际跳空/滑点可超预期。设置风险验证、收盘/盘中例外与减仓原则；固定2R不是止盈硬门槛。需要多日样本比较最大回撤、误触发、换手成本后才能晋升正式算法。

## 5. 状态与合同（V2）

READY：公司通过研究，突破或回调**在目标收盘日已经确认**，形成下一交易日有条件的有效 `entry_zone`、`entry_trigger`、`max_entry_price`、`invalidation_price`、`invalidation_rule`、`initial_risk_pct`和`exit_plan`；READY并非市价买入指令。

WAIT：候选合格但未突破、回调尚未确认、短时过热或结构成本太高；原因只允许 `WAIT_BREAKOUT`、`WAIT_PULLBACK`、`WAIT_CONFIRMATION`、`WAIT_RISK_REWARD`；不得由原WAIT_MARGIN、WAIT_PRICE冒充新原因。对于不能准确计算入场条件的公司，UNCERTAIN而非编造价位。

UNCERTAIN：缺关键量价、研究/价日期不符或入场/失效价无法建立；DROP：已证伪直接主题关联、硬过滤失败或已确认结构失效。筛出并不等于任何必买信号。

独立版本化schema：
- 正式结果规划路径 `research/trend_buy_formal_result.json`，`schema_version=trend_buy_result_v2`；在晋升前仅在 `research/shadow/` 输出试验结果，标 `production_eligible=false`。
- 正式交接规划路径 `research/trend_buy_handoff.json`，`schema_version=trend_buy_handoff_v2`，只可从同日 `status=COMPLETE` 且已readback的正式result投影其 READY+WAIT，禁止携带旧 `reasonable_buy_range` 或 `low_risk_buy_range` 字段。
- 传递字段必须有 `trade_date/source_run_id/source_formal_blob_sha`、rank、code、公司/主题/行业身份、status、wait_reason、类型、入场计划与退出计划。冻结身份顺序完全一致。
- 盘中快照须读取**当前已切换版本**的handoff并进行相同 schema/Gate；存储和提示必须保留新旧两套字段独立命名，不把趋势入场价误作估值合理区。盘中只负责触发/等待/风险提示，不自动下单、不重新研判公司或估值。
- 每次run须从最新有效上游handoff重算、全部审计通过才发布；报告全部READY/WAIT/UNCERTAIN/DROP、覆盖率和等待原因，不能为了出READY提前停止。
- 写入必须先JSON序列化和反解析、Coverage/Gate检查，更新前读目标最新SHA，成功后取得新commit与blob SHA且完整回读，才报告PERSISTED。失败不覆盖最后一版有效榜单。

## 6. 迁移和晋升顺序

1. **SHADOW**：新增规则与引擎，补每日聚合价格结构的自动生成，CI校验典型突破/回踩/高开/缺数据/假突破、跨日期隔离。
2. **PAPER**：使用已发布10/09候选及当日冻结视图进行不泄漏未来信息的对照；反复在不同市场环境进行样本外分析。旧正式结果、旧handoff、盘中监控不改变。
3. **PRODUCTION**：只有价格视图日期和数据完整性、真实案例买点检验、跨交易日risk/return验证、新版result与handoff投影、盘中快照消费与执行规则、新旧历史衔接均PASSED，才将单一定时任务从“A股低风险买点榜”更名为“A股趋势买点榜”；保留07:00/19:00、Asia/Shanghai、交易日Gate。盘中任务保持原时间，不在一次未经验证的迁移中停用所有监控。

冻结期间不造新的“今天”行情；当前测试用阈值与模型尚未证明优于旧规则时明确标 `NOT_PROMOTED`。

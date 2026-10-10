# A股趋势买点榜｜唯一正式业务规则

## 1. 目标
每日从已核验行业与符合公司硬过滤的股票中寻找**当前可执行或即将形成的趋势买点**，而非过去涨幅最高的公司。新入场优先级每天独立计算；先行股放量分歧后可能让位于新启动与修复候选，但分歧不等于趋势结束。移出新建仓榜不等于要求持仓者卖出。

## 2. 唯一执行链
1. 读取同一完整交易日的 research/trend_handoff.json；按 TREND_HANDOFF_ROUTING_OVERRIDE.md 路由申万三级行业。行业状态仅由原行业研究确定，下游不得擅自升级。
2. 校验 data/low_risk/index.json、manifest和全部part，读取一次并Freeze公司working set；不得用旧行情、缺失部分或未来证据。
3. 按 PRE_SCREEN_RESEARCH_SCOPE_OVERRIDE.md 执行原有公司硬过滤、45%增长/25%质量/20%估值匹配/10%趋势健康评分。所有hard-eligible公司均由Python利用已生成的技术摘要轻量计算买点机会分（35%入场/风险、30%价格结构、20%量价、15%相对强弱），再以70%机会分+30%原基本面分在每个三级行业前置动态选Top5（第6名与第5名分差≤0.03时并列）。仅入选者需要深度业务研究，非入选者记PRE_SCREENED_OUT。
4. 数据层 scripts/build_full_market_price_structure.py 在每日完整日K写入后计算一次全市场紧凑价量证据：近3/5日涨跌、之前5日表现、上涨/下跌日量能、1/5日量比、近3日收盘质量、10日回撤、近5日高点/20日低点、相对强弱与MA20/MA60。后续模型只消费汇总字段，不重复读取完整日K。每只候选要求120根完整有效K线和同日冻结价格一致。
5. 只对前置动态Top5入选公司核实主题商业关联、公告、财务和重大风险。明确NOT_SUPPORTED者剔除并依同三级行业轻量排名递补，缺少资料的新入选者记RESEARCH_PENDING并阻断正式发布，不允许自动使用旧名单替代。未入选的股票不需要深度研究、不得误标为UNCERTAIN。
6. 按最新价量数据确定个股阶段：INITIATING（启动）、PULLBACK（分歧回踩）、REACCELERATING（承接后再加速）、REPAIRING（结构修复）、COOLING（新入场优势下降）、FAILED（确认结构失效）、TRANSITION（证据尚不足）。MA20/MA60是背景而非淘汰红线；单纯低于MA60不得直接DROP，单日放量也不得直接宣布有效趋势。
7. 独立核实BREAKOUT和PULLBACK有效入场条件，计算真实触发价、条件区、最高买入价、失效价、初始风险、出口计划。板块只有“趋势确认”才允许READY；候选行业只能WAIT。短线距离MA20超过8%、chase=high、风险大于6%或上方已知阻力小于1.5R均暂缓。止损不可伪造；无可靠价格不升级READY。
8. 前置动态Top5深研完成后，按**趋势主题**跨各申万三级行业对当下的新入场机会进行重新比较：READY优先，其他候选以阶段、触发距离、有效风险边界排序；明显COOLING/FAILED不得占新买入名额。每主题最多五只合格股票，少于五只照实返回。输出 top5_by_theme 和每主题一个focus_watchlist，完全没有合格机会时为NO_CURRENT_BUY_OPPORTUNITY。每日重新计算，不继承前次选股。
9. 正式结果READY/WAIT/UNCERTAIN/DROP只覆盖前置动态Top5实际深研名单，审计单独保留所有hard-eligible的轻量得分、落选、递补和核查状态；最终主题Top5只能从研究合格者中选择。必须经过fresh_company_research、working_set_frozen、pre_screen_coverage、company_research_coverage、structure_same_day、no_future_evidence、json_schema_valid全部Gate。有效完整结果唯一写 research/trend_buy_formal_result.json，提交后READBACK校验run_id、日期、blob SHA和名单；不完整直接报错，不能借昨日结果冒充今日。
10. 仅完整19:00研究通过且正式结果READBACK后，scripts/trend_buy_handoff.py从动态主题Top5中提取READY/WAIT形成 research/trend_buy_handoff.json，仍遵守trend_buy_handoff_v2交易字段契约。盘中只按INTRADAY_MONITOR_CANONICAL.md监测交接名单，不重新选股或自动下单。早7:00只复核前一交易日，不新发布handoff。

## 3. 状态含义
- READY：经证据核实，行业趋势确认且价格形态、合理区间、结构失效及风险全部就绪；仅下一交易日条件性入场，非无条件买单。
- WAIT：当前未满足买点但存在可靠主题/结构观察价值；包括MA60下方的修复、启动未确认、分歧后的等待承接。
- UNCERTAIN：业务或关键结构缺失，不得补造数据。
- DROP：业务关联被证伪、重大硬风险或已验证结构失效；MA60和单日回落均不是充分淘汰理由。
- COOLING与正式WAIT是不同维度；暂停新建仓优先排名不直接命令已持有的用户止盈止损。持仓退出根据独立结构保护、业务逻辑证伪与风险预算执行。

## 4. 交易时间与异常
北京时间07:00只用前一完整交易日；19:00用当天已完成行情发布，非正式交易日不把旧数值当新信号。研究证据、市场数据、代码审计、GitHub提交或READBACK任何一项关键失败，不写新正式结果或handoff。连续多日行情指标只是形态代理，不证明实际资金身份，也尚未证明超额收益；生产参数须通过严格截至当日日K的历史回放验证。
